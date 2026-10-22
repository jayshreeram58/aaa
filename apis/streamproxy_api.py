"""
Personal Standalone API: Universal Anti-CORS Stream Proxy
Injects required Origin / Referer headers on the fly for Hotstar, NetMirror & Anime.
Port: 8006
"""

import sys
from aiohttp import web, ClientSession, ClientTimeout

async def handle_proxy(request):
    """GET /stream?platform={hotstar|net|anime}&url={target_url}"""
    target_url = request.query.get("url", "").strip()
    platform = request.query.get("platform", "").strip().lower()

    if not target_url:
        return web.Response(text="Missing 'url' query parameter", status=400)

    forward_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    if platform in ["hotstar", "jio"]:
        forward_headers["Origin"] = "https://www.hotstar.com"
        forward_headers["Referer"] = "https://www.hotstar.com/"
    elif platform == "net":
        forward_headers["Referer"] = "https://net52.cc/"
    elif platform == "anime":
        forward_headers["Origin"] = "https://ultracloud.cc"
        forward_headers["Referer"] = "https://ultracloud.cc/"

    if "Range" in request.headers:
        forward_headers["Range"] = request.headers["Range"]

    timeout = ClientTimeout(total=45)
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
        return web.Response(text=f"Proxy error: {e}", status=502)

def create_app():
    app = web.Application()
    app.router.add_get("/stream", handle_proxy)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8006
    print(f"🛡️ [Personal API] Universal Stream Proxy running on http://127.0.0.1:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)
