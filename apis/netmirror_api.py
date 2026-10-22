"""
Personal Standalone API: NetMirror (net.4umovies.site)
Resolves 1080p HLS Streams & Multi-subtitles from NetMirror.
Port: 8002
"""

import sys
import os
import asyncio
import urllib.parse
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fourmovies_network import NetMirrorClient

net = NetMirrorClient()

def json_res(data, status=200):
    return web.json_response(data, status=status, headers={"Access-Control-Allow-Origin": "*"})

async def handle_search(request):
    """GET /search?q={query}"""
    q = request.query.get("q", "").strip()
    if not q:
        return json_res({"error": "Missing query parameter 'q'"}, status=400)
    results = await asyncio.to_thread(net.search, q)
    return json_res({"success": True, "query": q, "count": len(results), "results": results})

async def handle_resolve(request):
    """GET /resolve/{id} or /resolve/{id}?ep={ep_id}"""
    content_id = request.match_info.get("id")
    ep_id = request.query.get("ep")
    try:
        data = await asyncio.to_thread(net.resolve_stream, content_id, ep_id)
        data["requiredHeaders"] = {"Referer": "https://net52.cc/"}
        data["validity"] = "6-12 hours"
        return json_res(data)
    except Exception as e:
        return json_res({"success": False, "error": str(e)}, status=500)

def create_app():
    app = web.Application()
    app.router.add_get("/search", handle_search)
    app.router.add_get("/resolve/{id}", handle_resolve)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8002
    print(f"🎬 [Personal API] NetMirror Server running on http://127.0.0.1:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)
