"""
Personal Standalone API: SonyLIV (Direct Official Engine)
Generates Official JWT Tokens, Akamai EdgeAuth Signed DASH & HLS Streams, and Catalogs.
Port: 8001
"""

import sys
import asyncio
from aiohttp import web
from direct_sonyliv import DirectSonyLIV

sony = DirectSonyLIV()

def json_res(data, status=200):
    return web.json_response(data, status=status, headers={"Access-Control-Allow-Origin": "*"})

async def handle_token(request):
    """GET /token -> Get current official SonyLIV security token"""
    token = await asyncio.to_thread(sony.get_security_token)
    return json_res({"success": True, "token": token, "source": "official_apiv2.sonyliv.com"})

async def handle_show(request):
    """GET /show/{id} -> Get show metadata & seasons"""
    show_id = request.match_info.get("id", "1700000084")
    try:
        data = await asyncio.to_thread(sony.get_show_details, show_id)
        return json_res({"success": True, "data": data})
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

async def handle_season_episodes(request):
    """GET /season/{id}/episodes?offset=0&limit=100"""
    season_id = request.match_info.get("id")
    offset = int(request.query.get("offset", 0))
    limit = int(request.query.get("limit", 100))
    try:
        eps = await asyncio.to_thread(sony.get_season_episodes, season_id, offset, limit)
        return json_res({"success": True, "seasonId": season_id, "count": len(eps), "episodes": eps})
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

async def handle_stream(request):
    """GET /stream/{id} -> Generate direct DASH MPD & HLS stream URLs"""
    video_id = request.match_info.get("id")
    try:
        stream = await asyncio.to_thread(sony.resolve_video_stream, video_id)
        return json_res(stream)
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

def create_app():
    app = web.Application()
    app.router.add_get("/token", handle_token)
    app.router.add_get("/show/{id}", handle_show)
    app.router.add_get("/season/{id}/episodes", handle_season_episodes)
    app.router.add_get("/stream/{id}", handle_stream)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    print(f"🎬 [Personal API] SonyLIV Server running on http://127.0.0.1:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)
