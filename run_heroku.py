"""
Course Wallah Downloader Bot - Universal Heroku Runner
Handles both Heroku Web and Worker dynos seamlessly:
1. Starts a lightweight HTTP health-check server on $PORT to satisfy Heroku R10 Boot timeout.
2. Runs the multi-bot Telegram engine (main.py) concurrently in the asyncio loop.
"""

import os
import sys
import asyncio
import logging
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
)
logger = logging.getLogger("HerokuRunner")

async def health_check_handler(request):
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Course Wallah Downloader Bot</title>
  <style>
    body {
      background: radial-gradient(circle at center, #0f172a 0%, #020617 100%);
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      text-align: center;
    }
    .card {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 20px;
      padding: 40px;
      max-width: 480px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.6);
      backdrop-filter: blur(12px);
    }
    h1 { font-size: 24px; font-weight: 800; color: #818cf8; margin-bottom: 12px; }
    .status-badge {
      display: inline-block;
      padding: 6px 16px;
      border-radius: 20px;
      background: rgba(16, 185, 129, 0.2);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 16px;
    }
    p { font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0; }
  </style>
</head>
<body>
  <div class="card">
    <div class="status-badge">● BOT RUNNING &amp; ONLINE 24/7</div>
    <h1>⚡ Course Wallah Downloader</h1>
    <p>High-Performance Academic Video &amp; PDF Downloader Telegram Bot with Single-Pass Watermarking &amp; Multi-Bot Scalability.</p>
  </div>
</body>
</html>"""
    return web.Response(text=html_content, content_type="text/html")

async def api_health_handler(request):
    return web.json_response({
        "status": "online",
        "service": "Course Wallah Downloader Bot",
        "platform": "Heroku",
        "dyno": os.environ.get("DYNO", "web.1"),
        "bot_active": True
    })

async def start_web_server(port: int):
    app = web.Application()
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", api_health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ Heroku Web Health Server listening on port {port}")

async def main():
    port_str = os.environ.get("PORT")
    if port_str:
        try:
            port = int(port_str)
            await start_web_server(port)
        except Exception as e:
            logger.warning(f"Failed to start health web server on port {port_str}: {e}")

    # Launch bot engine
    from main import start_all_bots, idle
    logger.info("🚀 Launching Course Wallah Telegram Multi-Bot Engine...")
    await start_all_bots()
    await idle()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped cleanly.")
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}", exc_info=True)
        sys.exit(1)
