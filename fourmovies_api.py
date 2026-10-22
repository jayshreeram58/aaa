"""
Unified REST API Server for 4uMovies Network Platforms
Provides clean REST endpoints + live streaming header proxy for:
1. NetMirror (net.4umovies.site)
2. Mastii OTT Pro (masti.4umovies.site)
3. AnimeKai (anime.4umovies.site)
4. SonyLIV (sony.4umovies.site)
5. DesiTV (desitv.4umovies.site)

Run standalone:
    python fourmovies_api.py [port]
"""

import os
import sys
import json
import asyncio
import logging
import urllib.parse
from aiohttp import web, ClientSession, ClientTimeout

from fourmovies_network import (
    NetMirrorClient,
    MastiiClient,
    AnimeKaiClient,
    SonyLIVClient,
    DesiTVClient
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fourmovies_api")

net_client = NetMirrorClient()
masti_client = MastiiClient()
anime_client = AnimeKaiClient()
sony_client = SonyLIVClient()
desitv_client = DesiTVClient()


def json_response(data: dict, status: int = 200) -> web.Response:
    """Standard JSON response helper with CORS headers."""
    return web.json_response(data, status=status, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    })


# =====================================================================
# 1. NetMirror Endpoints
# =====================================================================
async def handle_net_search(request: web.Request) -> web.Response:
    """GET /api/net/search?q={query}"""
    q = request.query.get("q", "").strip()
    if not q:
        return json_response({"error": "Query parameter 'q' is required"}, status=400)
    
    results = await asyncio.to_thread(net_client.search, q)
    return json_response({
        "success": True,
        "platform": "netmirror",
        "query": q,
        "count": len(results),
        "results": results
    })


async def handle_net_resolve(request: web.Request) -> web.Response:
    """GET /api/net/resolve?id={id}&ep={epId}"""
    content_id = request.query.get("id", "").strip()
    ep_id = request.query.get("ep", "").strip() or None
    if not content_id:
        return json_response({"error": "Parameter 'id' is required"}, status=400)
    
    try:
        stream_data = await asyncio.to_thread(net_client.resolve_stream, content_id, ep_id)
        direct_url = stream_data.get("directStreamUrl")
        if direct_url:
            host = request.host
            scheme = request.scheme
            stream_data["universalStreamUrl"] = f"{scheme}://{host}/api/proxy/stream?platform=net&url={urllib.parse.quote(direct_url)}"
            stream_data["requiredHeaders"] = {"Referer": "https://net52.cc/"}
            stream_data["tokenValidity"] = "6-12 hours"
        return json_response(stream_data)
    except Exception as e:
        logger.error(f"Net resolve error: {e}")
        return json_response({"success": False, "error": str(e)}, status=502)


# =====================================================================
# 2. Mastii OTT Pro Endpoints
# =====================================================================
async def handle_masti_shows(request: web.Request) -> web.Response:
    """GET /api/masti/shows"""
    shows = await asyncio.to_thread(masti_client.list_shows)
    return json_response({
        "success": True,
        "platform": "mastii_ott",
        "count": len(shows),
        "shows": shows
    })


async def handle_masti_episodes(request: web.Request) -> web.Response:
    """GET /api/masti/episodes?season_id={season_id}"""
    season_id = request.query.get("season_id", "").strip()
    if not season_id:
        return json_response({"error": "Parameter 'season_id' is required"}, status=400)
    
    episodes = await asyncio.to_thread(masti_client.get_season_episodes, season_id)
    return json_response({
        "success": True,
        "platform": "mastii_ott",
        "season_id": season_id,
        "count": len(episodes),
        "episodes": episodes
    })


async def handle_masti_resolve(request: web.Request) -> web.Response:
    """GET /api/masti/resolve?id={content_id}"""
    content_id = request.query.get("id", "").strip()
    if not content_id:
        return json_response({"error": "Parameter 'id' is required"}, status=400)
    
    stream_info = await asyncio.to_thread(masti_client.get_stream, content_id)
    if stream_info:
        stream_info["success"] = True
        stream_info["platform"] = "mastii_ott"
        stream_info["requiredHeaders"] = None
        stream_info["tokenValidity"] = "PERMANENT (Never expires)"
    return json_response(stream_info or {"success": False, "error": "Not found"})


# =====================================================================
# 3. AnimeKai Endpoints
# =====================================================================
async def handle_anime_search(request: web.Request) -> web.Response:
    """GET /api/anime/search?q={query}&limit={limit}"""
    q = request.query.get("q", "").strip()
    limit = int(request.query.get("limit", 15))
    if not q:
        return json_response({"error": "Query parameter 'q' is required"}, status=400)
    
    results = await asyncio.to_thread(anime_client.search, q, limit)
    return json_response({
        "success": True,
        "platform": "animekai",
        "query": q,
        "count": len(results),
        "results": results
    })


async def handle_anime_play(request: web.Request) -> web.Response:
    """GET /api/anime/play?id={anime_id}&ep={episode_num}"""
    anime_id = request.query.get("id", "").strip()
    ep_num = int(request.query.get("ep", 1))
    if not anime_id:
        return json_response({"error": "Parameter 'id' is required"}, status=400)
    
    stream_info = await asyncio.to_thread(anime_client.get_stream, anime_id, ep_num)
    stream_info["platform"] = "animekai"
    stream_info["tokenValidity"] = "4-6 hours"
    
    # Inject universal proxy stream url for each server
    host = request.host
    scheme = request.scheme
    for s in stream_info.get("streams", []):
        raw_u = s.get("url")
        if raw_u:
            s["universalStreamUrl"] = f"{scheme}://{host}/api/proxy/stream?platform=anime&url={urllib.parse.quote(raw_u)}"
    
    return json_response(stream_info)


# =====================================================================
# 4. SonyLIV Endpoints
# =====================================================================
async def handle_sony_episodes(request: web.Request) -> web.Response:
    """GET /api/sony/episodes?show={show_id}"""
    show_id = request.query.get("show", "1700000084").strip()
    data = await asyncio.to_thread(sony_client.get_show_episodes, show_id)
    return json_response(data)


async def handle_sony_stream(request: web.Request) -> web.Response:
    """GET /api/sony/stream?id={content_id}"""
    content_id = request.query.get("id", "1090548214").strip()
    manifest_url = sony_client.get_stream_manifest_url(content_id)
    return json_response({
        "success": True,
        "platform": "sonyliv",
        "id": content_id,
        "manifest_url": manifest_url,
        "format": "MPEG-DASH (MPD)",
        "requiredHeaders": None,
        "tokenValidity": "PERMANENT (Dynamic Live Proxy)"
    })


# =====================================================================
# 5. DesiTV Endpoints
# =====================================================================
async def handle_desitv_serials(request: web.Request) -> web.Response:
    """GET /api/desitv/serials"""
    catalog = await asyncio.to_thread(desitv_client.get_catalog)
    return json_response({
        "success": True,
        "platform": "desitv",
        "data": catalog
    })


async def handle_desitv_resolve(request: web.Request) -> web.Response:
    """GET /api/desitv/resolve?url={episode_url}"""
    ep_url = request.query.get("url", "").strip()
    if not ep_url:
        return json_response({"error": "Parameter 'url' is required"}, status=400)
    
    res = await asyncio.to_thread(desitv_client.resolve_stream, ep_url)
    return json_response(res)


# =====================================================================
# 6. Universal Streaming Header Proxy (Zero-Config Playback)
# =====================================================================
async def handle_stream_proxy(request: web.Request) -> web.StreamResponse:
    """
    GET /api/proxy/stream?platform={net|anime|masti}&url={target_url}
    Injects required Origin/Referer headers automatically on the fly!
    Enables any player (VLC, Safari, Chrome, ExoPlayer, Smart TV) to play
    restricted streams without setting headers manually.
    """
    target_url = request.query.get("url", "").strip()
    platform = request.query.get("platform", "").strip().lower()
    if not target_url:
        return web.Response(text="Missing url parameter", status=400)

    forward_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    if platform == "net":
        forward_headers["Referer"] = "https://net52.cc/"
    elif platform == "anime":
        forward_headers["Origin"] = "https://ultracloud.cc"
        forward_headers["Referer"] = "https://ultracloud.cc/"

    # Forward Range headers if present (for seeking)
    if "Range" in request.headers:
        forward_headers["Range"] = request.headers["Range"]

    timeout = ClientTimeout(total=30)
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.get(target_url, headers=forward_headers) as upstream:
                resp = web.StreamResponse(status=upstream.status)
                for h in ["Content-Type", "Content-Length", "Accept-Ranges", "Content-Range"]:
                    if h in upstream.headers:
                        resp.headers[h] = upstream.headers[h]
                
                resp.headers["Access-Control-Allow-Origin"] = "*"
                await resp.prepare(request)

                async for chunk in upstream.content.iter_chunked(65536):
                    await resp.write(chunk)
                await resp.write_eof()
                return resp
    except Exception as e:
        logger.error(f"Proxy error for {target_url}: {e}")
        return web.Response(text=f"Proxy error: {e}", status=502)


# =====================================================================
# Health & Status Endpoint
# =====================================================================
async def handle_health(request: web.Request) -> web.Response:
    """GET /api/health"""
    return json_response({
        "status": "healthy",
        "service": "4uMovies Network Unified API",
        "platforms": {
            "netmirror": {
                "base": "https://net.4umovies.site",
                "stream_validity": "6-12 hours",
                "required_headers": {"Referer": "https://net52.cc/"}
            },
            "mastii_ott": {
                "base": "https://masti.4umovies.site",
                "stream_validity": "PERMANENT (Zero token/No expiry)",
                "required_headers": "None"
            },
            "animekai": {
                "base": "https://anime.4umovies.site",
                "stream_validity": "4-6 hours",
                "required_headers": {"Origin": "https://ultracloud.cc", "Referer": "https://ultracloud.cc/"}
            },
            "sonyliv": {
                "base": "https://sony.4umovies.site",
                "stream_validity": "PERMANENT (Live Dynamic Manifest)",
                "required_headers": "None"
            },
            "desitv": {
                "base": "https://desitv.4umovies.site",
                "stream_validity": "12-24 hours",
                "required_headers": "None"
            }
        }
    })


def create_app() -> web.Application:
    app = web.Application()
    # NetMirror
    app.router.add_get("/api/net/search", handle_net_search)
    app.router.add_get("/api/net/resolve", handle_net_resolve)
    # Mastii OTT
    app.router.add_get("/api/masti/shows", handle_masti_shows)
    app.router.add_get("/api/masti/episodes", handle_masti_episodes)
    app.router.add_get("/api/masti/resolve", handle_masti_resolve)
    # AnimeKai
    app.router.add_get("/api/anime/search", handle_anime_search)
    app.router.add_get("/api/anime/play", handle_anime_play)
    # SonyLIV
    app.router.add_get("/api/sony/episodes", handle_sony_episodes)
    app.router.add_get("/api/sony/stream", handle_sony_stream)
    # DesiTV
    app.router.add_get("/api/desitv/serials", handle_desitv_serials)
    app.router.add_get("/api/desitv/resolve", handle_desitv_resolve)
    # Stream Proxy
    app.router.add_get("/api/proxy/stream", handle_stream_proxy)
    # Health
    app.router.add_get("/api/health", handle_health)
    return app


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    print(f"🚀 Starting 4uMovies Network Unified REST API Server on port {port}...")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)
