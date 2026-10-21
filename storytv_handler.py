import os
import re
import sys
import json
import time
import shutil
import asyncio
import logging
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

from pyrogram import Client, filters
from pyrogram.types import Message

logger = logging.getLogger(__name__)

# =========================================================================
# PATH CONFIGURATION & SAFE DIRECTORY INITIALIZATION
# =========================================================================
BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "storytv_shows_catalog.json"
SESSION_PATH = BASE_DIR / "storytv_session.json"
DATA_SHOWS_DIR = BASE_DIR / "data" / "shows"
EXTRACTED_SHOWS_DIR = BASE_DIR / "extracted_shows"
TEMP_DOWNLOAD_DIR = BASE_DIR / "downloads" / "storytv"

# Optional local experiment repository (if exists on dev environment)
EXPERIMENT_API_DIR = Path("B:/Projects/experiment/storytv-api")
EXPERIMENT_SHOWS_DIR = EXPERIMENT_API_DIR / "data" / "shows"

# Create directories safely
DATA_SHOWS_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_SHOWS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
if EXPERIMENT_API_DIR.exists():
    try:
        EXPERIMENT_SHOWS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

OFFICIAL_API = "https://api.storytv.asia"
STORYTV_PORTAL_API = "https://storytv.4umovies.site/api"

# Verified active JWT fallback
DEFAULT_JWT = (
    "eyJhbGciOiJIUzI1NiJ9.eyJjcmVhdGVkRGF0ZSI6IjIwMjUtMTEtMjkgMDg6MjQ6MjcuNTY2Iiwic2Vzc2lvbklkIjoiMjIzMjk2NzIyIiwi"
    "ZGV2aWNlSWQiOiI3MmY4Yjg3M2MxMTE4ZGEyIiwic3ViIjoiMzM2OTExNTUiLCJleHAiOjE3OTI4NjQxNzB9.85fi95pTZXrZbW-6MrUms5oHOnXNyb2VcHvMcS1BhYw"
)

# Global stop flag
_STOP_REQUESTED = False

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

# =========================================================================
# CATALOG & JSON DEDUPLICATION LOGIC
# =========================================================================

def load_all_catalog_shows() -> List[Dict[str, Any]]:
    """
    Loads all catalog shows (1,215 shows).
    Checks local file first; if missing (e.g. in fresh Colab clone),
    can load from fallback index.
    """
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            logger.error(f"Error loading catalog from {CATALOG_PATH}: {e}")

    # Fallback to local data/shows_index.json if exists
    alt_index = BASE_DIR / "data" / "shows_index.json"
    if alt_index.exists():
        try:
            with open(alt_index, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass

    return []

def get_uploaded_episode_indices(show_id: str) -> Set[int]:
    """
    Checks JSON file on disk for this show.
    Returns a set of episode indices that are already uploaded to Telegram
    (having telegramMessageId, telegramUrl, or status == 'uploaded').
    This guarantees ZERO duplicate downloads and seamless resume!
    """
    uploaded: Set[int] = set()
    candidate_paths = [
        DATA_SHOWS_DIR / f"{show_id}.json",
        EXTRACTED_SHOWS_DIR / f"{show_id}.json",
    ]
    if EXPERIMENT_API_DIR.exists():
        candidate_paths.append(EXPERIMENT_SHOWS_DIR / f"{show_id}.json")

    for p in candidate_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for ep in data.get("episodes", []):
                        if ep.get("status") == "uploaded" or ep.get("telegramMessageId") or ep.get("telegramUrl"):
                            if "index" in ep:
                                uploaded.add(int(ep["index"]))
            except Exception as e:
                logger.warning(f"Error reading existing show JSON {p}: {e}")
    return uploaded

def load_show_json_data(show_id: str) -> Dict[str, Any]:
    """Loads full existing show JSON dict or returns fresh structure."""
    candidate_paths = [
        DATA_SHOWS_DIR / f"{show_id}.json",
        EXTRACTED_SHOWS_DIR / f"{show_id}.json",
    ]
    if EXPERIMENT_API_DIR.exists():
        candidate_paths.append(EXPERIMENT_SHOWS_DIR / f"{show_id}.json")

    for p in candidate_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"showId": str(show_id), "episodes": []}

def save_show_json_data(show_id: str, show_obj: Dict[str, Any]):
    """
    Saves updated show JSON to disk immediately after each episode upload.
    Ensures that if Colab or the bot stops, no progress is ever lost.
    """
    dest_dirs = [DATA_SHOWS_DIR, EXTRACTED_SHOWS_DIR]
    if EXPERIMENT_API_DIR.exists():
        dest_dirs.append(EXPERIMENT_SHOWS_DIR)

    # Google Drive Mirror on Colab (if mounted)
    colab_drive_dir = Path("/content/drive/MyDrive/course_wallah_storytv/data/shows")
    if Path("/content/drive/MyDrive").exists():
        dest_dirs.append(colab_drive_dir)

    for dest_dir in dest_dirs:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            with open(dest_dir / f"{show_id}.json", "w", encoding="utf-8") as f:
                json.dump(show_obj, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Could not save show JSON in {dest_dir}: {e}")

# =========================================================================
# METADATA EXTRACTION & STREAM RESOLUTION
# =========================================================================

def fetch_show_episodes_page(show_id: str, cursor: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetches a page of episode metadata with Akamai-signed m3u8 streams.
    Primary source: storytv.4umovies.site/api/metadata/{showId} (has all unlocked episodes)
    Secondary fallback: official api.storytv.asia API
    """
    # 1. Try 4umovies high-yield API first
    try:
        url_4u = f"{STORYTV_PORTAL_API}/metadata/{show_id}"
        if cursor is not None:
            url_4u += f"?cursor={cursor}&dir=NEXT"
        req = urllib.request.Request(url_4u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            content = data.get("data", {}).get("content", [])
            if content:
                return content
    except Exception as e:
        logger.debug(f"4umovies metadata fetch notice for {show_id}: {e}")

    # 2. Fallback to Official StoryTV API
    try:
        url_off = f"{OFFICIAL_API}/feedservice/v1/episode/metadata/{show_id}"
        if cursor is not None:
            url_off += f"?cursor={cursor}&dir=NEXT"
        req_off = urllib.request.Request(url_off, headers=get_headers())
        with urllib.request.urlopen(req_off, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") == 200 and data.get("data"):
                return data["data"].get("content", [])
    except Exception as e:
        logger.warning(f"Official API metadata fetch error for {show_id}: {e}")

    return []

# =========================================================================
# VIDEO DOWNLOADER (yt-dlp)
# =========================================================================

def download_video_stream(stream_url: str, output_path: Path) -> bool:
    """
    Downloads an HLS stream to an MP4 video file using yt-dlp.
    Handles separate audio+video manifests (bv*+ba/b).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "-f", "bestvideo[height<=720]+bestaudio/bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        stream_url,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=240, check=False)
        if output_path.exists() and output_path.stat().st_size > 50000:
            return True
        logger.warning(f"yt-dlp download stderr: {res.stderr.decode('utf-8', 'ignore')[:200]}")
    except Exception as e:
        logger.error(f"yt-dlp download failed: {e}")
    return False

# =========================================================================
# TELEGRAM COMMAND HANDLERS: /storytv & /stopstorytv
# =========================================================================

async def stop_storytv_cmd(client: Client, message: Message):
    """Command to cleanly stop the automated StoryTV batch process."""
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    await message.reply_text(
        "🛑 <b>StoryTV Batch Process Stop Requested!</b>\n\n"
        "The current upload will finish safely and the loop will pause.\n"
        "All progress is saved in JSON files. Run <code>/storytv</code> anytime to resume without duplicates!"
    )

async def storytv_cmd(client: Client, message: Message):
    """
    Automated StoryTV Downloader & Channel Uploader:
    - User gives /storytv (optionally with Channel ID, or prompted ONCE for Channel ID).
    - Automatically processes all 1,215 shows sequentially.
    - Zero manual intervention per show or per episode.
    - Smart Deduplication: Checks {showId}.json on disk.
      - If an episode already has a telegramMessageId or telegramUrl, it is SKIPPED instantly!
      - If pending, it downloads and uploads it to the Channel, and writes to {showId}.json immediately.
    - If the bot stops or crashes, re-running /storytv resumes seamlessly with NO duplicates!
    """
    global _STOP_REQUESTED
    _STOP_REQUESTED = False

    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    # Check command arguments
    args = message.text.split(maxsplit=2)
    arg_1 = args[1].strip() if len(args) > 1 else ""

    target_channel_id = None
    target_single_show_id = None

    # Check if arg_1 is channel ID (starts with -100 or negative number)
    if arg_1.startswith("-100") or (arg_1.startswith("-") and arg_1[1:].isdigit()):
        target_channel_id = int(arg_1)
    elif arg_1.isdigit() and len(arg_1) > 8:
        target_channel_id = int(f"-100{arg_1}")
    elif arg_1.isdigit():
        target_single_show_id = arg_1
    elif arg_1 and arg_1 != "all":
        target_single_show_id = arg_1

    # Check environment variable fallback for channel ID
    if not target_channel_id:
        env_ch = os.environ.get("STORYTV_CHANNEL_ID") or os.environ.get("TARGET_CHANNEL_ID")
        if env_ch and (env_ch.startswith("-") or env_ch.isdigit()):
            try:
                target_channel_id = int(env_ch)
            except Exception:
                pass

    editable = await message.reply_text(
        "🎬 <b>StoryTV Automated Downloader & Channel Uploader</b>\n\n"
        "<i>Initializing automated engine & verifying catalog...</i>"
    )

    try:
        # STEP 1: If Channel ID is not yet known, prompt ONCE
        if not target_channel_id:
            await editable.edit_text(
                "🎬 <b>StoryTV Automated Downloader Engine</b>\n\n"
                "<blockquote>📢 <b>Send Destination Telegram Channel ID</b>:\n"
                "<i>Example: <code>-1002233445566</code> (Bot must be Admin with Post permission)\n"
                "Or send <code>/d</code> to upload right in this chat.</i></blockquote>\n\n"
                "<i>⚡ Once provided, the bot will run completely autonomously for all shows and skip already uploaded episodes!</i>"
            )
            ch_msg = await client.listen(chat_id=chat_id, user_id=user_id, timeout=120)
            ch_text = ch_msg.text.strip()
            await ch_msg.delete()

            if ch_text.lower() in ["/cancel", "cancel"]:
                await editable.edit_text("❌ <b>Operation cancelled.</b>")
                return

            target_channel_id = chat_id if ch_text == "/d" else int(ch_text)

        # STEP 2: Load Catalog Shows
        catalog = load_all_catalog_shows()
        if not catalog:
            await editable.edit_text("❌ <b>StoryTV catalog (storytv_shows_catalog.json) not found or empty!</b>")
            return

        if target_single_show_id:
            shows_to_process = [
                s for s in catalog
                if str(s.get("showId")) == target_single_show_id
                or target_single_show_id.lower() in str(s.get("showTitle", "")).lower()
            ]
            if not shows_to_process:
                shows_to_process = [{
                    "showId": target_single_show_id,
                    "showTitle": f"Show {target_single_show_id}",
                    "totalEpisodes": 45,
                    "genre": "Short Drama"
                }]
        else:
            shows_to_process = catalog

        total_shows = len(shows_to_process)
        clean_ch_id = str(target_channel_id).replace("-100", "")

        await editable.edit_text(
            f"🚀 <b>StoryTV Autonomous Downloader Started!</b>\n\n"
            f"📚 <b>Total Shows in Queue:</b> {total_shows}\n"
            f"📢 <b>Target Channel ID:</b> <code>{target_channel_id}</code>\n"
            f"🛡️ <b>Smart JSON Deduplication:</b> Enabled (Skips completed episodes instantly)\n"
            f"🛑 <i>Send /stopstorytv anytime to pause safely.</i>\n\n"
            f"<i>Starting sequential download & upload loop...</i>"
        )

        global_uploaded = 0
        global_skipped = 0
        last_progress_edit = time.time()

        # =========================================================================
        # AUTONOMOUS SHOW ITERATION LOOP
        # =========================================================================
        for show_idx, show_item in enumerate(shows_to_process, 1):
            if _STOP_REQUESTED:
                await message.reply_text("🛑 <b>StoryTV Batch stopped cleanly upon user request.</b>")
                break

            show_id = str(show_item.get("showId"))
            show_title = show_item.get("showTitle", f"Show {show_id}")
            genre = show_item.get("genre", "Short Drama")
            catalog_total_eps = int(show_item.get("totalEpisodes", 0) or 0)

            # 1. Check existing JSON for this show on disk
            existing_uploaded = get_uploaded_episode_indices(show_id)
            show_obj = load_show_json_data(show_id)
            show_obj["showId"] = show_id
            show_obj["showTitle"] = show_title
            show_obj["genre"] = genre
            show_obj["channelId"] = str(target_channel_id)

            episodes_map = {int(ep["index"]): ep for ep in show_obj.get("episodes", []) if "index" in ep}

            # If all episodes for this show are already uploaded -> Skip show entirely!
            if catalog_total_eps > 0 and len(existing_uploaded) >= catalog_total_eps:
                global_skipped += catalog_total_eps
                logger.info(f"Show '{show_title}' ({show_id}) already complete ({len(existing_uploaded)}/{catalog_total_eps}). Skipping.")
                continue

            # Update live status card periodically
            now = time.time()
            if now - last_progress_edit > 6:
                last_progress_edit = now
                try:
                    await editable.edit_text(
                        f"🎬 <b>StoryTV Engine Running ({show_idx}/{total_shows} Shows)</b>\n\n"
                        f"📺 <b>Current Show:</b> <b>{show_title}</b> (ID: <code>{show_id}</code>)\n"
                        f"📊 <b>Show Progress:</b> {len(existing_uploaded)}/{catalog_total_eps or '?'} Episodes Uploaded\n"
                        f"⚡ <b>Session Uploaded:</b> {global_uploaded} | ⏭️ <b>Total Skipped:</b> {global_skipped}\n"
                        f"📢 <b>Channel:</b> <code>{target_channel_id}</code>\n"
                        f"🛑 <i>Send /stopstorytv to pause anytime.</i>"
                    )
                except Exception:
                    pass

            # 2. Page through episodes for this show
            cursor: Optional[int] = None
            consecutive_empty = 0

            while True:
                if _STOP_REQUESTED:
                    break

                batch = fetch_show_episodes_page(show_id, cursor=cursor)
                if not batch:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                    await asyncio.sleep(1)
                    continue
                consecutive_empty = 0

                for target_meta in batch:
                    if _STOP_REQUESTED:
                        break

                    ep_idx = int(target_meta.get("index", 1))
                    stream_url = target_meta.get("epsUrl", "")

                    # DEDUPLICATION CHECK: If already uploaded in JSON -> SKIP INSTANTLY!
                    if ep_idx in existing_uploaded and episodes_map.get(ep_idx, {}).get("telegramUrl"):
                        global_skipped += 1
                        continue

                    if not stream_url:
                        continue

                    content_id = str(target_meta.get("contentId", ep_idx))
                    ep_title = target_meta.get("epsTitle", f"{show_title} - Episode {ep_idx}")
                    sub_txt = target_meta.get("subTxt", f"{ep_idx}/{catalog_total_eps or '?'}")
                    thumb_url = target_meta.get("thumb", "")

                    # Download video file locally
                    temp_video_file = TEMP_DOWNLOAD_DIR / f"{show_id}_ep_{ep_idx}_{int(time.time())}.mp4"
                    temp_thumb_file = TEMP_DOWNLOAD_DIR / f"{show_id}_thumb_{ep_idx}.jpg"

                    if thumb_url:
                        try:
                            urllib.request.urlretrieve(thumb_url, str(temp_thumb_file))
                        except Exception:
                            pass

                    download_ok = download_video_stream(stream_url, temp_video_file)
                    if not download_ok or not temp_video_file.exists():
                        if temp_thumb_file.exists():
                            try: temp_thumb_file.unlink()
                            except Exception: pass
                        continue

                    # Upload to Telegram Channel
                    caption = (
                        f"🎬 <b>{show_title}</b> — Episode {ep_idx}\n"
                        f"⚡ <b>Series:</b> {genre}\n"
                        f"📺 <b>Quality:</b> 720p HD Reel | 9:16\n"
                        f"🆔 <b>Show ID:</b> <code>{show_id}</code> &bull; <b>Episode:</b> {sub_txt}\n\n"
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

                        tg_link = f"https://t.me/c/{clean_ch_id}/{sent_msg.id}"
                        file_id = sent_msg.video.file_id if sent_msg.video else ""

                        # Record in Episode Map & Save JSON immediately
                        episodes_map[ep_idx] = {
                            "index": ep_idx,
                            "contentId": content_id,
                            "title": ep_title,
                            "label": sub_txt,
                            "telegramMessageId": sent_msg.id,
                            "telegramUrl": tg_link,
                            "fileId": file_id,
                            "streamUrl": stream_url,
                            "thumbnail": thumb_url,
                            "status": "uploaded",
                            "uploadedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }

                        existing_uploaded.add(ep_idx)
                        global_uploaded += 1

                        # Save updated JSON to disk immediately after each upload!
                        show_obj["totalEpisodes"] = max(catalog_total_eps, len(episodes_map))
                        show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        show_obj["episodes"] = [episodes_map[k] for k in sorted(episodes_map.keys())]
                        save_show_json_data(show_id, show_obj)

                    except Exception as up_err:
                        logger.error(f"Error uploading ep {ep_idx} of show {show_id}: {up_err}")
                    finally:
                        # Clean up disk files immediately (0 MB accumulation)
                        if temp_video_file.exists():
                            try: temp_video_file.unlink()
                            except Exception: pass
                        if temp_thumb_file.exists():
                            try: temp_thumb_file.unlink()
                            except Exception: pass

                    await asyncio.sleep(1.5)

                # Advance cursor to the last episode seen in this batch
                last_idx = batch[-1].get("index")
                if cursor is not None and last_idx <= cursor:
                    break
                cursor = last_idx

                # If reached catalog total, finish this show
                if catalog_total_eps > 0 and len(existing_uploaded) >= catalog_total_eps:
                    break

        # =========================================================================
        # BATCH COMPLETION SUMMARY
        # =========================================================================
        final_summary = (
            f"🎉 <b>StoryTV Engine Completed!</b>\n\n"
            f"📚 <b>Total Shows in Catalog:</b> {total_shows}\n"
            f"✅ <b>New Episodes Uploaded:</b> {global_uploaded}\n"
            f"⏭️ <b>Episodes Skipped (Already Uploaded):</b> {global_skipped}\n"
            f"📢 <b>Destination Channel:</b> <code>{target_channel_id}</code>\n"
            f"💾 <b>Local JSON Status:</b> All progress saved in data/shows/\n"
            f"🍿 <b>Zero Duplicate Guarantee:</b> Resumable anytime with /storytv"
        )
        await editable.edit_text(final_summary)

    except asyncio.TimeoutError:
        await editable.edit_text("⏱️ <b>Timed out waiting for Channel ID. Run /storytv again to resume.</b>")
    except Exception as e:
        logger.exception("StoryTV Batch Engine Error")
        await editable.edit_text(f"❌ <b>Error in StoryTV Engine:</b>\n<code>{str(e)}</code>")
