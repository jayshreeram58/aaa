"""
Personal Standalone API: AnimeKai (anime.4umovies.site)
Anime Search & Multi-Server Sub/Dub HLS Streaming Resolver.
Port: 8004
"""

import sys
import os
import asyncio
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fourmovies_network import AnimeKaiClient

anime = AnimeKaiClient()

def json_res(data, status=200):
    return web.json_response(data, status=status, headers={"Access-Control-Allow-Origin": "*"})

async def handle_search(request):
    """GET /search?q={query}&limit=15"""
    q = request.query.get("q", "").strip()
    limit = int(request.query.get("limit", 15))
    if not q:
        return json_res({"error": "Missing query parameter 'q'"}, status=400)
    results = await asyncio.to_thread(anime.search, q, limit)
    return json_res({"success": True, "query": q, "count": len(results), "results": results})

async def handle_play(request):
    """GET /play/{id}?ep=1"""
    anime_id = request.match_info.get("id")
    ep_num = int(request.query.get("ep", 1))
    try:
        data = await asyncio.to_thread(anime.get_stream, anime_id, ep_num)
        data["validity"] = "4-6 hours"
        data["requiredHeaders"] = {"Origin": "https://ultracloud.cc", "Referer": "https://ultracloud.cc/"}
        return json_res(data)
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

def create_app():
    app = web.Application()
    app.router.add_get("/search", handle_search)
    app.router.add_get("/play/{id}", handle_play)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8004
    print(f"🌸 [Personal API] AnimeKai Server running on http://127.0.0.1:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)
