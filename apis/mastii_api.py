"""
Personal Standalone API: Mastii OTT Pro (masti.4umovies.site)
AES-128-CBC Decrypted Master HLS Streams & Show Catalog.
Port: 8003
"""

import sys
import os
import asyncio
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fourmovies_network import MastiiClient

masti = MastiiClient()

def json_res(data, status=200):
    return web.json_response(data, status=status, headers={"Access-Control-Allow-Origin": "*"})

async def handle_shows(request):
    """GET /shows -> List all 112 Mastii OTT shows"""
    shows = await asyncio.to_thread(masti.list_shows)
    return json_res({"success": True, "count": len(shows), "shows": shows})

async def handle_episodes(request):
    """GET /season/{id}/episodes"""
    season_id = request.match_info.get("id")
    try:
        eps = await asyncio.to_thread(masti.get_season_episodes, season_id)
        return json_res({"success": True, "seasonId": season_id, "count": len(eps), "episodes": eps})
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

async def handle_stream(request):
    """GET /stream/{content_id} -> Decrypted Direct Master HLS URL"""
    content_id = request.match_info.get("content_id")
    try:
        info = await asyncio.to_thread(masti.get_stream, content_id)
        info["requiredHeaders"] = None
        info["validity"] = "PERMANENT (Lifetime / No Expiry)"
        return json_res(info)
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

def create_app():
    app = web.Application()
    app.router.add_get("/shows", handle_shows)
    app.router.add_get("/season/{id}/episodes", handle_episodes)
    app.router.add_get("/stream/{content_id}", handle_stream)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8003
    print(f"🎬 [Personal API] Mastii OTT Server running on http://127.0.0.1:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)
