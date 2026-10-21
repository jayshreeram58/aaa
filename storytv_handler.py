import os
import re
import sys
import json
import time
import shutil
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

from pyrogram import Client, filters
from pyrogram.types import Message

logger = logging.getLogger(__name__)

# Constants & Paths
BASE_DIR = Path(__file__).resolve().parent
EXPERIMENT_API_DIR = Path("B:/Projects/experiment/storytv-api")
STORYTV_DATA_SHOWS = EXPERIMENT_API_DIR / "data" / "shows"
CATALOG_PATH = BASE_DIR / "storytv_shows_catalog.json"
SESSION_PATH = BASE_DIR / "storytv_session.json"
EXTRACTED_SHOWS_DIR = BASE_DIR / "extracted_shows"

TEMP_DOWNLOAD_DIR = BASE_DIR / "downloads" / "storytv"
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
STORYTV_DATA_SHOWS.mkdir(parents=True, exist_ok=True)
EXTRACTED_SHOWS_DIR.mkdir(parents=True, exist_ok=True)

OFFICIAL_API = "https://api.storytv.asia"

# Fallback verified JWT
DEFAULT_JWT = (
    "eyJhbGciOiJIUzI1NiJ9.eyJjcmVhdGVkRGF0ZSI6IjIwMjUtMTEtMjkgMDg6MjQ6MjcuNTY2Iiwic2Vzc2lvbklkIjoiMjIzMjk2NzIyIiwi"
    "ZGV2aWNlSWQiOiI3MmY4Yjg3M2MxMTE4ZGEyIiwic3ViIjoiMzM2OTExNTUiLCJleHAiOjE3OTI4NjQxNzB9.85fi95pTZXrZbW-6MrUms5oHOnXNyb2VcHvMcS1BhYw"
)

def get_active_jwt() -> str:
    """Reads fresh active JWT from session file or returns verified fallback."""
    if SESSION_PATH.exists():
        try:
            with open(SESSION_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and "jwt" in data:
                    return data["jwt"]
        except Exception as e:
            logger.warning(f"Failed to read session file: {e}")
    return DEFAULT_JWT

def get_headers() -> Dict[str, str]:
    return {
        "model_name": "A5010",
        "brand": "OnePlus",
        "manf": "OnePlus",
        "appVersion": "60",
        "platform": "0",
        "deviceId": "72f8b873c1118da2",
        "os": "Android 9 (API 28)",
        "network_type": "WIFI",
        "Accept": "application/json",
        "User-Agent": "ktor-client",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_active_jwt()}",
        "ts": str(int(time.time())),
    }

def find_show_info(query: str) -> Optional[Dict[str, Any]]:
    """Finds show info from catalog by ID or title keyword."""
    query = str(query).strip().lower()
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                catalog = json.load(f)
                # First check exact ID match
                for s in catalog:
                    if str(s.get("showId", "")).strip().lower() == query:
                        return s
                # Next check title match
                for s in catalog:
                    if query in str(s.get("showTitle", "")).lower():
                        return s
        except Exception as e:
            logger.warning(f"Error querying catalog: {e}")

    # Fallback to direct API fetch
    try:
        import urllib.request
        url = f"{OFFICIAL_API}/feedservice/v1/episode/list/{query}"
        req = urllib.request.Request(url, headers=get_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode()).get("data", {})
            if data and "showTitle" in data:
                return {
                    "showId": str(data.get("showId", query)),
                    "showTitle": data.get("showTitle", f"Show {query}"),
                    "totalEpisodes": data.get("epCount", 40),
                    "genre": data.get("genre", "Short Drama"),
                    "poster": "",
                    "isFree": True,
                }
    except Exception as e:
        logger.warning(f"Direct API fetch error for show {query}: {e}")

    return None

def fetch_episode_metadata(show_id: str, cursor: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetches episode metadata with signed m3u8 streaming links from StoryTV API."""
    import urllib.request
    url = f"{OFFICIAL_API}/feedservice/v1/episode/metadata/{show_id}"
    if cursor is not None:
        url += f"?cursor={cursor}&dir=NEXT"

    try:
        req = urllib.request.Request(url, headers=get_headers())
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200 and data.get("data"):
                return data["data"].get("content", [])
    except Exception as e:
        logger.error(f"Error fetching episode metadata for {show_id}: {e}")
    return []

def download_video_stream(stream_url: str, output_path: Path) -> bool:
    """Downloads an HLS video stream to MP4 using yt-dlp."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        stream_url,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=240, check=False)
        if output_path.exists() and output_path.stat().st_size > 50000:
            return True
        logger.warning(f"yt-dlp stderr: {res.stderr.decode('utf-8', 'ignore')[:200]}")
    except Exception as e:
        logger.error(f"yt-dlp download failed: {e}")
    return False

def sync_repo_to_github(show_id: str, show_title: str) -> bool:
    """Commits and pushes updated show JSON files to GitHub repository."""
    if not (EXPERIMENT_API_DIR / ".git").exists():
        return False
    try:
        subprocess.run(["git", "add", "data/shows/"], cwd=str(EXPERIMENT_API_DIR), check=True, stdout=subprocess.DEVNULL)
        subprocess.run(
            ["git", "commit", "-m", f"update: Add Telegram stream URLs for {show_title} ({show_id})"],
            cwd=str(EXPERIMENT_API_DIR),
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["git", "push", "origin", "master"], cwd=str(EXPERIMENT_API_DIR), check=True, stdout=subprocess.DEVNULL)
        return True
    except Exception as e:
        logger.warning(f"Git push failed (non-critical): {e}")
        return False

# =========================================================================
# TELEGRAM COMMAND HANDLER: /storytv or /story
# =========================================================================

async def storytv_cmd(client: Client, message: Message):
    """
    Interactive StoryTV downloader and Telegram channel uploader:
    1. Prompts for Show ID or Title
    2. Prompts for Destination Telegram Channel ID
    3. Downloads each episode and uploads it to the Telegram Channel
    4. Records the Telegram message links into the show's JSON file on GitHub / Portal
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    # Parse initial argument if provided: e.g. /storytv 1974
    args = message.text.split(maxsplit=1)
    raw_query = args[1].strip() if len(args) > 1 else ""

    editable = await message.reply_text(
        "🎬 <b>StoryTV Downloader & Channel Uploader</b>\n\n"
        "<i>Initializing StoryTV engine...</i>"
    )

    try:
        # STEP 1: Get Show Query if not given in command line
        if not raw_query:
            await editable.edit_text(
                "🎬 <b>StoryTV Downloader & Channel Uploader</b>\n\n"
                "<blockquote>Please send the <b>Show ID</b> or <b>Show Name</b>:\n"
                "<i>Example: <code>1974</code> or <code>Cook Bana Crorepati</code></i></blockquote>\n\n"
                "<i>Send /cancel to abort.</i>"
            )
            input_msg = await client.listen(chat_id=chat_id, user_id=user_id, timeout=120)
            raw_query = input_msg.text.strip()
            await input_msg.delete()

            if raw_query.lower() in ["/cancel", "cancel"]:
                await editable.edit_text("❌ <b>Operation cancelled by user.</b>")
                return

        # Resolve Show Info
        await editable.edit_text(f"🔍 <i>Searching catalog for:</i> <code>{raw_query}</code>...")
        show_info = find_show_info(raw_query)

        if not show_info:
            await editable.edit_text(
                f"❌ <b>Show Not Found!</b>\n\n"
                f"Could not find any StoryTV show matching: <code>{raw_query}</code>\n"
                f"Please check the Show ID from the portal (e.g. <code>1974</code>) and try again."
            )
            return

        show_id = str(show_info.get("showId"))
        show_title = show_info.get("showTitle", f"Show {show_id}")
        genre = show_info.get("genre", "Short Drama")
        total_eps = int(show_info.get("totalEpisodes", 40) or 40)

        # STEP 2: Ask for Target Telegram Channel ID
        await editable.edit_text(
            f"🎬 <b>Found Show:</b> <b>{show_title}</b> (ID: <code>{show_id}</code>)\n"
            f"📊 <b>Total Episodes:</b> {total_eps} Episodes | <b>Genre:</b> {genre}\n\n"
            f"<blockquote>📢 <b>Send the Target Channel ID</b> where videos will be uploaded:\n"
            f"<i>Example: <code>-1002233445566</code> (Bot must be Admin with Post permission)\n"
            f"Or send <code>/d</code> to upload in this chat.</i></blockquote>"
        )

        ch_input_msg = await client.listen(chat_id=chat_id, user_id=user_id, timeout=120)
        ch_text = ch_input_msg.text.strip()
        await ch_input_msg.delete()

        if ch_text.lower() in ["/cancel", "cancel"]:
            await editable.edit_text("❌ <b>Operation cancelled.</b>")
            return

        target_channel_id = chat_id if ch_text == "/d" else int(ch_text)

        # STEP 3: Ask for Episode Range (Optional)
        await editable.edit_text(
            f"🎬 <b>{show_title}</b>\n"
            f"📢 <b>Destination:</b> <code>{target_channel_id}</code>\n\n"
            f"<blockquote>🔢 <b>Episode Range:</b>\n"
            f"Send range like <code>1-10</code> or send <code>/d</code> for <b>All {total_eps} Episodes</b>:</blockquote>"
        )

        range_input_msg = await client.listen(chat_id=chat_id, user_id=user_id, timeout=120)
        range_text = range_input_msg.text.strip()
        await range_input_msg.delete()

        start_ep = 1
        end_ep = total_eps

        if range_text != "/d" and "-" in range_text:
            try:
                parts = range_text.split("-")
                start_ep = max(1, int(parts[0].strip()))
                end_ep = min(total_eps, int(parts[1].strip()))
            except Exception:
                start_ep, end_ep = 1, total_eps

        total_to_process = end_ep - start_ep + 1

        # Load Existing Show JSON if available
        json_file_path = STORYTV_DATA_SHOWS / f"{show_id}.json"
        existing_show_data = {}
        if json_file_path.exists():
            try:
                with open(json_file_path, "r", encoding="utf-8") as f:
                    existing_show_data = json.load(f)
            except Exception:
                existing_show_data = {}

        episodes_map = {ep["index"]: ep for ep in existing_show_data.get("episodes", [])}

        await editable.edit_text(
            f"🚀 <b>Starting StoryTV Pipeline!</b>\n\n"
            f"🎬 <b>Show:</b> {show_title} (ID: <code>{show_id}</code>)\n"
            f"📦 <b>Episodes:</b> {start_ep} to {end_ep} ({total_to_process} items)\n"
            f"📢 <b>Channel ID:</b> <code>{target_channel_id}</code>\n"
            f"⏳ <i>Please wait while videos are downloaded, uploaded, and mapped to JSON...</i>"
        )

        uploaded_count = 0
        failed_count = 0

        # MAIN DOWNLOAD & UPLOAD LOOP
        for ep_idx in range(start_ep, end_ep + 1):
            status_text = (
                f"🎬 <b>{show_title}</b>\n"
                f"🔄 <b>Processing Episode {ep_idx} of {end_ep}</b>\n"
                f"✅ <i>Uploaded:</i> {uploaded_count} | ❌ <i>Failed:</i> {failed_count}\n"
                f"📢 <b>Channel:</b> <code>{target_channel_id}</code>"
            )
            try:
                await editable.edit_text(status_text)
            except Exception:
                pass

            # 1. Fetch Episode Stream Metadata
            meta_batch = fetch_episode_metadata(show_id, cursor=ep_idx - 1 if ep_idx > 1 else None)
            target_meta = None
            if meta_batch:
                target_meta = next((e for e in meta_batch if e.get("index") == ep_idx), meta_batch[0])

            if not target_meta or not target_meta.get("epsUrl"):
                logger.warning(f"Could not retrieve stream URL for ep {ep_idx}")
                failed_count += 1
                continue

            stream_url = target_meta.get("epsUrl")
            content_id = str(target_meta.get("contentId", ep_idx))
            ep_title = target_meta.get("epsTitle", f"{show_title} - Episode {ep_idx}")
            thumb_url = target_meta.get("thumb", "")

            # 2. Download Stream Locally
            temp_video_file = TEMP_DOWNLOAD_DIR / f"{show_id}_ep_{ep_idx}_{int(time.time())}.mp4"
            temp_thumb_file = TEMP_DOWNLOAD_DIR / f"{show_id}_thumb_{ep_idx}.jpg"

            # Download thumbnail
            if thumb_url:
                try:
                    import urllib.request
                    urllib.request.urlretrieve(thumb_url, str(temp_thumb_file))
                except Exception:
                    pass

            download_ok = download_video_stream(stream_url, temp_video_file)

            if not download_ok or not temp_video_file.exists():
                logger.error(f"Download failed for ep {ep_idx}")
                failed_count += 1
                if temp_thumb_file.exists():
                    temp_thumb_file.unlink()
                continue

            # 3. Upload Video to Target Telegram Channel
            caption = (
                f"🎬 <b>{show_title}</b> — Episode {ep_idx}\n"
                f"⚡ <b>Series:</b> {genre}\n"
                f"📺 <b>Quality:</b> 720p Full HD | 9:16 Reel\n"
                f"🆔 <b>Show ID:</b> <code>{show_id}</code> &bull; <b>Episode:</b> {ep_idx}/{total_eps}\n\n"
                f"🍿 <i>Uploaded via Course Wallah Bot</i>"
            )

            try:
                sent_msg = await client.send_video(
                    chat_id=target_channel_id,
                    video=str(temp_video_file),
                    caption=caption,
                    thumb=str(temp_thumb_file) if temp_thumb_file.exists() else None,
                    supports_streaming=True,
                )

                # Generate Telegram Web / Message link
                clean_ch_id = str(target_channel_id).replace("-100", "")
                tg_link = f"https://t.me/c/{clean_ch_id}/{sent_msg.id}"
                file_id = sent_msg.video.file_id if sent_msg.video else ""

                # 4. Update Show JSON Data Structure
                episodes_map[ep_idx] = {
                    "index": ep_idx,
                    "contentId": content_id,
                    "title": ep_title,
                    "label": f"{ep_idx}/{total_eps}",
                    "telegramMessageId": sent_msg.id,
                    "telegramUrl": tg_link,
                    "fileId": file_id,
                    "streamUrl": stream_url,
                    "thumbnail": thumb_url,
                    "status": "uploaded",
                    "uploadedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                uploaded_count += 1

                # Save updated JSON to both portal and bot storage
                updated_show_obj = {
                    "showId": show_id,
                    "showTitle": show_title,
                    "genre": genre,
                    "totalEpisodes": total_eps,
                    "channelId": str(target_channel_id),
                    "lastUpdated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "episodes": [episodes_map[k] for k in sorted(episodes_map.keys())],
                }

                # Save locally
                for dest_dir in [STORYTV_DATA_SHOWS, EXTRACTED_SHOWS_DIR]:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    with open(dest_dir / f"{show_id}.json", "w", encoding="utf-8") as out_f:
                        json.dump(updated_show_obj, out_f, ensure_ascii=False, indent=2)

            except Exception as upload_err:
                logger.error(f"Failed to upload episode {ep_idx}: {upload_err}")
                failed_count += 1
            finally:
                # Cleanup local temp files
                if temp_video_file.exists():
                    try:
                        temp_video_file.unlink()
                    except Exception:
                        pass
                if temp_thumb_file.exists():
                    try:
                        temp_thumb_file.unlink()
                    except Exception:
                        pass

            # Small delay between uploads
            await asyncio.sleep(2)

        # 5. Git Commit & Push JSON to GitHub
        git_synced = sync_repo_to_github(show_id, show_title)

        # 6. Send Final Completion Report
        clean_ch_id = str(target_channel_id).replace("-100", "")
        summary_msg = (
            f"🎉 <b>StoryTV Processing Completed!</b>\n\n"
            f"🎬 <b>Show Title:</b> <b>{show_title}</b>\n"
            f"🆔 <b>Show ID:</b> <code>{show_id}</code>\n"
            f"📊 <b>Uploaded:</b> <b>{uploaded_count}</b> / {total_to_process} Episodes\n"
            f"📢 <b>Channel:</b> <code>{target_channel_id}</code>\n"
            f"🔗 <b>First Episode Link:</b> <a href='https://t.me/c/{clean_ch_id}/{episodes_map.get(start_ep, {}).get('telegramMessageId', '')}'>Open in Channel</a>\n\n"
            f"🌐 <b>Portal JSON Status:</b> {'✅ Auto-Pushed to GitHub' if git_synced else 'Saved locally in data/shows/'}\n"
            f"🍿 <b>Live Web Player:</b> <code>storytv_show.html?id={show_id}</code>"
        )
        await editable.edit_text(summary_msg, disable_web_page_preview=False)

    except asyncio.TimeoutError:
        await editable.edit_text("⏱️ <b>Timed out waiting for input. Please try again with /storytv.</b>")
    except Exception as e:
        logger.exception("StoryTV Command Error")
        await editable.edit_text(f"❌ <b>Error occurred during StoryTV extraction:</b>\n<code>{str(e)}</code>")
