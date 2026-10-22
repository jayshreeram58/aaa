"""
Personal Standalone API: YouTube 4K Cloud Downloader Engine
Background workers, 4K/1080p/MP3 conversion, progress tracking & direct downloads.
Port: 8005
"""

import os
import sys
import uuid
import asyncio
import urllib.parse
from aiohttp import web
import yt_dlp

YT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads", "yt_cloud")
os.makedirs(YT_DIR, exist_ok=True)
JOBS = {}

def json_res(data, status=200):
    return web.json_response(data, status=status, headers={"Access-Control-Allow-Origin": "*"})

async def handle_info(request):
    """POST /info with {"url": "..."}"""
    try:
        body = await request.json()
    except Exception:
        return json_res({"ok": False, "error": "Invalid JSON"}, status=400)

    url = body.get("url", "").strip()
    if not url:
        return json_res({"ok": False, "error": "Missing 'url' parameter"}, status=400)

    def _extract():
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'no_warnings': True}) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        formats = info.get("formats", [])
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

        return json_res({
            "ok": True,
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration_string"),
            "channel": info.get("uploader") or info.get("channel"),
            "videoQualities": video_qualities,
            "audioQualities": audio_qualities
        })
    except Exception as e:
        return json_res({"ok": False, "error": str(e)}, status=500)

async def handle_download(request):
    """POST /download with {"url": "...", "format": "mp4", "quality": "1080"}"""
    try:
        body = await request.json()
    except Exception:
        return json_res({"success": False, "error": "Invalid JSON"}, status=400)

    url = body.get("url", "").strip()
    fmt = body.get("format", "mp4").strip().lower()
    quality = body.get("quality", "1080").strip()
    if not url:
        return json_res({"success": False, "error": "Missing 'url' parameter"}, status=400)

    job_id = str(uuid.uuid4())[:12]
    job_folder = os.path.join(YT_DIR, job_id)
    os.makedirs(job_folder, exist_ok=True)

    JOBS[job_id] = {
        "id": job_id, "status": "downloading", "progress": 0, "filename": None, "filepath": None, "error": None
    }

    def _worker():
        try:
            def hook(d):
                if d.get("status") == "downloading":
                    tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    cur = d.get("downloaded_bytes", 0)
                    if tot > 0:
                        JOBS[job_id]["progress"] = int((cur / tot) * 100)
                elif d.get("status") == "finished":
                    JOBS[job_id]["progress"] = 99
                    JOBS[job_id]["status"] = "processing"

            outtmpl = os.path.join(job_folder, "%(title)s.%(ext)s")
            if fmt == "mp3":
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': outtmpl,
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality if quality in ['128', '256', '320'] else '192'}],
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
                downloaded = ydl.prepare_filename(res)
                if fmt == "mp3":
                    downloaded = os.path.splitext(downloaded)[0] + ".mp3"
                else:
                    if not os.path.exists(downloaded):
                        alt = os.path.splitext(downloaded)[0] + ".mp4"
                        if os.path.exists(alt): downloaded = alt

            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["progress"] = 100
            JOBS[job_id]["filename"] = os.path.basename(downloaded)
            JOBS[job_id]["filepath"] = downloaded
        except Exception as e:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(e)

    asyncio.create_task(asyncio.to_thread(_worker))
    return json_res({"success": True, "jobId": job_id})

async def handle_status(request):
    """GET /status/{jobId}"""
    job_id = request.match_info.get("jobId")
    job = JOBS.get(job_id)
    if not job:
        return json_res({"error": "Job not found"}, status=404)

    host = request.host
    scheme = request.scheme
    res = dict(job)
    if job.get("status") == "completed" and job.get("filename"):
        fn = urllib.parse.quote(job["filename"])
        res["downloadUrl"] = f"{scheme}://{host}/file/{job_id}/{fn}"
    res.pop("filepath", None)
    return json_res(res)

async def handle_file(request):
    """GET /file/{jobId}/{filename}"""
    job_id = request.match_info.get("jobId")
    filename = request.match_info.get("filename")
    job = JOBS.get(job_id)
    if not job or not job.get("filepath") or not os.path.exists(job["filepath"]):
        return web.Response(text="File not found or expired", status=404)
    return web.FileResponse(job["filepath"], headers={"Content-Disposition": f'attachment; filename="{filename}"'})

def create_app():
    app = web.Application()
    app.router.add_post("/info", handle_info)
    app.router.add_post("/download", handle_download)
    app.router.add_get("/status/{jobId}", handle_status)
    app.router.add_get("/file/{jobId}/{filename}", handle_file)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8005
    print(f"⚡ [Personal API] YouTube Cloud Downloader running on http://127.0.0.1:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)
