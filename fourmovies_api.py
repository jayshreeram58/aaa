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

    elif platform in ["hotstar", "jio"]:
        forward_headers["Origin"] = "https://www.hotstar.com"
        forward_headers["Referer"] = "https://www.hotstar.com/"

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
# 7. YouTube 4K Cloud Downloader Engine (Identical to asmultiverse.site)
# =====================================================================
import uuid
import yt_dlp

YT_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads", "yt_cloud")
os.makedirs(YT_DOWNLOAD_DIR, exist_ok=True)
YT_JOBS = {}


async def handle_yt_info(request: web.Request) -> web.Response:
    """POST /api/yt/info with body {"url": "https://www.youtube.com/watch?v=..."}"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    url = body.get("url", "").strip()
    if not url:
        return json_response({"ok": False, "error": "Missing 'url' parameter"}, status=400)

    def _extract():
        ydl_opts = {'quiet': True, 'skip_download': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        formats = info.get("formats", [])
        
        # Collect available video resolutions
        seen_res = set()
        video_qualities = []
        for f in formats:
            h = f.get("height")
            if h and h not in seen_res:
                seen_res.add(h)
                label = f"{h}p"
                if h >= 2160: label += " (4K Ultra HD)"
                elif h >= 1440: label += " (2K Quad HD)"
                elif h >= 1080: label += " (Full HD)"
                video_qualities.append({"label": label, "value": str(h), "selected": h == 1080})

        video_qualities.sort(key=lambda x: int(x["value"]), reverse=True)

        audio_qualities = [
            {"label": "320 kbps (Studio HD)", "value": "320"},
            {"label": "256 kbps (High Quality)", "value": "256"},
            {"label": "128 kbps (Fast Download)", "value": "128", "selected": True}
        ]

        subtitles = list((info.get("subtitles") or {}).keys())

        return json_response({
            "ok": True,
            "isPlaylist": bool(info.get("_type") == "playlist"),
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration_string"),
            "durationSeconds": info.get("duration"),
            "channel": info.get("uploader") or info.get("channel"),
            "videoQualities": video_qualities,
            "audioQualities": audio_qualities,
            "subtitles": subtitles,
            "hasSubtitles": bool(subtitles)
        })
    except Exception as e:
        logger.error(f"YT Info error: {e}")
        return json_response({"ok": False, "error": str(e)}, status=500)


async def handle_yt_download(request: web.Request) -> web.Response:
    """POST /api/yt/download"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"success": False, "error": "Invalid JSON"}, status=400)

    url = body.get("url", "").strip()
    fmt = body.get("format", "mp4").strip().lower()
    quality = body.get("quality", "1080").strip()

    if not url:
        return json_response({"success": False, "error": "Missing 'url' parameter"}, status=400)

    job_id = str(uuid.uuid4())[:12]
    job_folder = os.path.join(YT_DOWNLOAD_DIR, job_id)
    os.makedirs(job_folder, exist_ok=True)

    YT_JOBS[job_id] = {
        "id": job_id,
        "status": "initializing",
        "progress": 0,
        "filename": None,
        "downloadUrl": None,
        "error": None
    }

    def _worker():
        try:
            YT_JOBS[job_id]["status"] = "downloading"
            
            def hook(d):
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    if total > 0:
                        YT_JOBS[job_id]["progress"] = int((downloaded / total) * 100)
                elif d.get("status") == "finished":
                    YT_JOBS[job_id]["progress"] = 99
                    YT_JOBS[job_id]["status"] = "processing"

            outtmpl = os.path.join(job_folder, "%(title)s.%(ext)s")
            if fmt == "mp3":
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': outtmpl,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': quality if quality in ['128', '256', '320'] else '192',
                    }],
                    'progress_hooks': [hook],
                    'quiet': True
                }
            else:
                ydl_opts = {
                    'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best',
                    'outtmpl': outtmpl,
                    'merge_output_format': 'mp4',
                    'progress_hooks': [hook],
                    'quiet': True
                }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(res)
                if fmt == "mp3":
                    downloaded_file = os.path.splitext(downloaded_file)[0] + ".mp3"
                else:
                    if not os.path.exists(downloaded_file):
                        alt = os.path.splitext(downloaded_file)[0] + ".mp4"
                        if os.path.exists(alt):
                            downloaded_file = alt

            filename = os.path.basename(downloaded_file)
            YT_JOBS[job_id]["status"] = "completed"
            YT_JOBS[job_id]["progress"] = 100
            YT_JOBS[job_id]["filename"] = filename
            YT_JOBS[job_id]["filepath"] = downloaded_file
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            YT_JOBS[job_id]["status"] = "failed"
            YT_JOBS[job_id]["error"] = str(e)

    asyncio.create_task(asyncio.to_thread(_worker))

    return json_response({
        "success": True,
        "jobId": job_id
    })


async def handle_yt_status(request: web.Request) -> web.Response:
    """GET /api/yt/status/{jobId}"""
    job_id = request.match_info.get("jobId", "").strip()
    job = YT_JOBS.get(job_id)
    if not job:
        return json_response({"error": "Job not found"}, status=404)

    host = request.host
    scheme = request.scheme
    res = dict(job)
    if job.get("status") == "completed" and job.get("filename"):
        encoded_fn = urllib.parse.quote(job["filename"])
        res["downloadUrl"] = f"{scheme}://{host}/api/yt/file/{job_id}/{encoded_fn}"

    res.pop("filepath", None)
    return json_response(res)


async def handle_yt_file(request: web.Request) -> web.Response:
    """GET /api/yt/file/{jobId}/{filename}"""
    job_id = request.match_info.get("jobId", "").strip()
    filename = request.match_info.get("filename", "").strip()
    job = YT_JOBS.get(job_id)

    if not job or not job.get("filepath") or not os.path.exists(job["filepath"]):
        return web.Response(text="File not found or expired", status=404)

    return web.FileResponse(job["filepath"], headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })


# =====================================================================
# Health & Status Endpoint
# =====================================================================
async def handle_health(request: web.Request) -> web.Response:
    """GET /api/health"""
    return json_response({
        "status": "healthy",
        "service": "4uMovies Network & Media Hub Unified API",
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
            },
            "youtube_downloader": {
                "engine": "yt-dlp cloud worker (4K/1080p/MP3)",
                "endpoints": ["/api/yt/info", "/api/yt/download", "/api/yt/status/{jobId}", "/api/yt/file/{jobId}/{fn}"]
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
    # Stream Proxy (Hotstar, NetMirror, Anime)
    app.router.add_get("/api/proxy/stream", handle_stream_proxy)
    # YouTube 4K Downloader Engine (Identical to asmultiverse)
    app.router.add_post("/api/yt/info", handle_yt_info)
    app.router.add_post("/api/yt/download", handle_yt_download)
    app.router.add_get("/api/yt/status/{jobId}", handle_yt_status)
    app.router.add_get("/api/yt/file/{jobId}/{filename}", handle_yt_file)
    # Health
    app.router.add_get("/api/health", handle_health)
    return app


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    print(f"🚀 Starting 4uMovies Network & YouTube Hub API Server on port {port}...")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)

