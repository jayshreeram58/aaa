"""
Master API Hub Runner
Run all personal APIs together on Port 8888, or run any individual API standalone!

Usage:
  python apis/run_all.py              # Runs all 6 APIs mounted on Port 8888
  python apis/run_all.py --sony       # Runs SonyLIV API standalone on Port 8001
  python apis/run_all.py --net        # Runs NetMirror API standalone on Port 8002
  python apis/run_all.py --masti      # Runs Mastii OTT API standalone on Port 8003
  python apis/run_all.py --anime      # Runs AnimeKai API standalone on Port 8004
  python apis/run_all.py --yt         # Runs YouTube Downloader API on Port 8005
  python apis/run_all.py --proxy      # Runs Stream Proxy on Port 8006
"""

import sys
import os
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sonyliv_api
import netmirror_api
import mastii_api
import anime_api
import ytdownloader_api
import streamproxy_api

def create_master_app():
    master = web.Application()

    # Mount modular sub-applications
    master.add_subapp("/sony", sonyliv_api.create_app())
    master.add_subapp("/net", netmirror_api.create_app())
    master.add_subapp("/masti", mastii_api.create_app())
    master.add_subapp("/anime", anime_api.create_app())
    master.add_subapp("/yt", ytdownloader_api.create_app())
    master.add_subapp("/proxy", streamproxy_api.create_app())

    async def handle_index(request):
        return web.json_response({
            "status": "online",
            "name": "Personal Streaming & Media Hub API",
            "endpoints": {
                "sonyliv": "/sony (Direct official token & streams)",
                "netmirror": "/net (1080p movies & shows)",
                "mastii": "/masti (AES decrypted originals)",
                "anime": "/anime (Multi-server sub/dub)",
                "youtube": "/yt (4K/1080p cloud downloader)",
                "proxy": "/proxy (Hotstar/NetMirror/Anime anti-CORS proxy)"
            }
        }, headers={"Access-Control-Allow-Origin": "*"})

    master.router.add_get("/", handle_index)
    master.router.add_get("/health", handle_index)
    return master

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--sony" in args:
        web.run_app(sonyliv_api.create_app(), host="0.0.0.0", port=8001)
    elif "--net" in args:
        web.run_app(netmirror_api.create_app(), host="0.0.0.0", port=8002)
    elif "--masti" in args:
        web.run_app(mastii_api.create_app(), host="0.0.0.0", port=8003)
    elif "--anime" in args:
        web.run_app(anime_api.create_app(), host="0.0.0.0", port=8004)
    elif "--yt" in args:
        web.run_app(ytdownloader_api.create_app(), host="0.0.0.0", port=8005)
    elif "--proxy" in args:
        web.run_app(streamproxy_api.create_app(), host="0.0.0.0", port=8006)
    else:
        port = int(args[0]) if args and args[0].isdigit() else 8888
        print(f"🚀 [Master API Hub] All 6 Modular APIs mounted together on http://127.0.0.1:{port}")
        web.run_app(create_master_app(), host="0.0.0.0", port=port)
