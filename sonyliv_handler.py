"""
Course Wallah - Automated SonyLIV Downloader & Channel Uploader
Direct official integration with SonyLIV API (apiv2.sonyliv.com) - Zero third-party dependency.

Features:
- Commands: /sonyliv, /sony, /stopsonyliv, /stopsony, /recoversonyliv, /recoversony
- Fetches all seasons and episodes for any SonyLIV show (URL or Show ID)
- Resolves official Akamai EdgeAuth signed HLS M3U8 video streams
- Live real-time percentage progress bar for both downloading and uploading
- Smart Deduplication: Skips already uploaded episodes using local JSON and remote GitHub repository
- Automatic single-pass watermarking & official thumbnail generation
- Auto-syncs episode data to data/shows/sony_{show_id}.json and pushes to GitHub
- 500MB low-disk safe: Deletes temp files immediately post-upload
"""

import os
import re
import sys
import json
import time
import shutil
import asyncio
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from direct_sonyliv import DirectSonyLIV
from vars import WATERMARK_TEXT, WATERMARK_FILE, CREDIT, TEMP_DIR, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH
import itsgolu as helper

logger = logging.getLogger("SonyLIVHandler")

BASE_DIR = Path(__file__).resolve().parent
DATA_SHOWS_DIR = BASE_DIR / "data" / "shows"
TEMP_DOWNLOAD_DIR = BASE_DIR / "downloads" / "sonyliv"

DATA_SHOWS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Global stop flag
_SONY_STOP_REQUESTED = False

# GitHub synchronization
SONY_GITHUB_REPO = os.environ.get("GITHUB_REPO", "ramjipatel-tech/course-wallah-platform").strip()
SONY_GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()


def make_progress_bar(percent: float, bar_length: int = 12) -> str:
    """Generates clean ASCII progress bar with filled and empty characters."""
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round(bar_length * (pct / 100.0)))
    unfilled = bar_length - filled
    return "█" * filled + "░" * unfilled


def hrb(value: Optional[float | int], digits: int = 2) -> str:
    """Formats bytes to human readable string (KB, MB, GB)."""
    if value is None:
        return "0 B"
    try:
        val = float(value)
    except (ValueError, TypeError):
        return "0 B"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(val) < 1024.0:
            return f"{val:.{digits}f} {unit}" if unit != "B" else f"{int(val)} {unit}"
        val /= 1024.0
    return f"{val:.{digits}f} PB"


def hrt(seconds: Optional[float | int]) -> str:
    """Formats seconds to human readable time string."""
    if seconds is None or seconds < 0:
        return "00s"
    try:
        sec = int(seconds)
    except (ValueError, TypeError):
        return "00s"

    hours = sec // 3600
    minutes = (sec % 3600) // 60
    rem_sec = sec % 60

    if hours > 0:
        return f"{hours}h {minutes:02d}m {rem_sec:02d}s"
    if minutes > 0:
        return f"{minutes:02d}m {rem_sec:02d}s"
    return f"{rem_sec:02d}s"


# =========================================================================
# GITHUB & REMOTE REST API SYNCHRONIZATION
# =========================================================================

def github_put_file_api(file_path: str, content_dict: Any, commit_msg: str) -> bool:
    """Pushes or updates a JSON file on GitHub using GitHub REST API."""
    token = GITHUB_TOKEN or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        return False

    url = f"https://api.github.com/repos/{SONY_GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CourseWallah-SonyLIVSync/1.0"
    }

    # 1. Check existing file SHA
    sha = None
    try:
        req = urllib.request.Request(f"{url}?ref={SONY_GITHUB_BRANCH}", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode())
                sha = body.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            logger.warning(f"Error checking existing GitHub file {file_path}: {e}")
    except Exception as e:
        logger.warning(f"GitHub SHA check failed for {file_path}: {e}")

    # 2. Encode file content to Base64
    import base64
    raw_bytes = json.dumps(content_dict, indent=2, ensure_ascii=False).encode("utf-8")
    b64_content = base64.b64encode(raw_bytes).decode("utf-8")

    payload = {
        "message": commit_msg,
        "content": b64_content,
        "branch": SONY_GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha

    try:
        data_json = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_json, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in [200, 201]:
                logger.info(f"✅ Successfully synced {file_path} to GitHub repo: {SONY_GITHUB_REPO}")
                return True
    except Exception as e:
        logger.warning(f"Failed to push {file_path} to GitHub: {e}")
    return False


def sync_sony_show_to_github(show_id: str, show_title: str, show_obj: dict) -> bool:
    """Saves show JSON locally and pushes to GitHub repository."""
    file_name = f"sony_{show_id}.json"
    local_path = DATA_SHOWS_DIR / file_name

    # 1. Save local atomic copy
    temp_path = DATA_SHOWS_DIR / f"{file_name}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(show_obj, f, indent=2, ensure_ascii=False)
    temp_path.replace(local_path)

    # 2. Sync to GitHub
    rel_path = f"data/shows/{file_name}"
    uploaded_eps = len(show_obj.get("episodes", []))
    msg = f"sync(sonyliv): update {show_title} ({show_id}) - {uploaded_eps} episodes"
    return github_put_file_api(rel_path, show_obj, msg)


def load_sony_show_json(show_id: str) -> dict:
    """Loads existing SonyLIV show JSON from local disk or GitHub."""
    file_name = f"sony_{show_id}.json"
    local_path = DATA_SHOWS_DIR / file_name
    if local_path.exists():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Try fetching from remote GitHub
    try:
        url = f"https://raw.githubusercontent.com/{SONY_GITHUB_REPO}/{SONY_GITHUB_BRANCH}/data/shows/{file_name}"
        req = urllib.request.Request(url, headers={"User-Agent": "CourseWallah/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                with open(local_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return data
    except Exception:
        pass

    return {
        "platform": "sonyliv",
        "showId": show_id,
        "showTitle": "",
        "channelId": "",
        "lastUpdated": "",
        "episodes": []
    }


# =========================================================================
# 📺 SONY TV POPULAR SHOW CATALOG
# =========================================================================

POPULAR_SONY_SHOWS = [
    {"title": "Taarak Mehta Ka Ooltah Chashmah", "id": "1700000084", "icon": "🎭", "alias": ["tmkoc", "taarak", "mehta", "jethalal", "tarak"]},
    {"title": "CID", "id": "1700000196", "icon": "🕵️", "alias": ["cid", "pradyuman", "daya", "abhijeet", "c.i.d."]},
    {"title": "Crime Patrol Satark", "id": "1700000108", "icon": "🚔", "alias": ["crime patrol", "crime patrol satark", "satark", "crimepatrol"]},
    {"title": "Crime Patrol Dial 100", "id": "1700000076", "icon": "🚨", "alias": ["dial 100", "dial100", "crime dial 100"]},
    {"title": "The Kapil Sharma Show", "id": "1700000083", "icon": "🎤", "alias": ["kapil", "tkss", "kapil sharma", "the kapil sharma show"]},
    {"title": "Scam 1992: Harshad Mehta", "id": "1700000292", "icon": "📈", "alias": ["scam", "1992", "harshad", "scam 1992"]},
    {"title": "Adaalat (KD Pathak)", "id": "1700000091", "icon": "🧑‍⚖️", "alias": ["adaalat", "kd pathak", "court", "adalat"]},
    {"title": "Aladdin - Naam Toh Suna Hoga", "id": "1700000001", "icon": "🧙", "alias": ["aladdin", "naam toh suna hoga", "aladin"]},
    {"title": "Tenali Rama", "id": "1700000003", "icon": "⚔️", "alias": ["tenali", "rama", "tenalirama"]},
    {"title": "Baalveer", "id": "1700000071", "icon": "🦸", "alias": ["baalveer", "balveer", "baal veer"]},
    {"title": "Vighnaharta Ganesh", "id": "1700000078", "icon": "🐘", "alias": ["ganesh", "vighnaharta", "vighnaharta ganesh"]},
    {"title": "Aahat", "id": "1700000144", "icon": "👻", "alias": ["aahat", "horror"]},
    {"title": "Bharat Ka Veer Putra Maharana Pratap", "id": "1700000143", "icon": "👑", "alias": ["maharana pratap", "pratap", "maharana"]},
    {"title": "Suryaputra Karn", "id": "1700000150", "icon": "🏹", "alias": ["karn", "suryaputra", "suryaputra karn"]},
    {"title": "India's Best Dancer", "id": "1700000180", "icon": "💃", "alias": ["dancer", "ibd", "indias best dancer"]},
    {"title": "Yeh Un Dinon Ki Baat Hai", "id": "1700000106", "icon": "💖", "alias": ["yudkbh", "yeh un dinon", "sameer naina"]},
    {"title": "Mere Sai - Shraddha Aur Saburi", "id": "1700000107", "icon": "🙏", "alias": ["sai", "mere sai", "shirdi"]},
    {"title": "Sankatmochan Mahabali Hanuman", "id": "1700000109", "icon": "🐒", "alias": ["hanuman", "sankatmochan"]},
    {"title": "Beyhadh", "id": "1700000007", "icon": "💔", "alias": ["beyhadh", "maya", "jennifer"]},
    {"title": "Patiala Babes", "id": "1700000060", "icon": "👭", "alias": ["patiala babes", "babes", "patiala"]}
]


def extract_sony_show_id(text: str) -> Optional[str]:
    """Extracts SonyLIV show ID from raw number, URL, or popular show title/alias."""
    if not text:
        return None
    clean = text.strip()

    # 1. Direct numeric ID
    if clean.isdigit():
        return clean

    # 2. Extract from SonyLIV URL (e.g. /shows/cid-1700000196 or ?show=1700000196)
    m = re.search(r"(\d{9,12})", clean)
    if m:
        return m.group(1)

    m2 = re.search(r"[?&]show=(\d+)", clean)
    if m2:
        return m2.group(1)

    # 3. Match against popular shows catalog
    clean_lower = clean.lower()
    for show in POPULAR_SONY_SHOWS:
        if clean_lower == show["title"].lower():
            return show["id"]
        for al in show.get("alias", []):
            if al == clean_lower or clean_lower.startswith(al) or al in clean_lower:
                return show["id"]

    return None


def build_sony_catalog_panel() -> tuple[str, InlineKeyboardMarkup]:
    """Builds a rich show list with IDs and interactive 1-click download buttons."""
    header = (
        "📺 <b>SONYLIV FULL SHOW DOWNLOADER & BACKUP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🌟 <b>Top Popular Shows & Show IDs:</b>\n\n"
    )

    lines = []
    for idx, s in enumerate(POPULAR_SONY_SHOWS, 1):
        lines.append(f"{idx}. {s['icon']} <b>{s['title']}</b> ➔ <code>{s['id']}</code>")

    footer = (
        "\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>👇 <b>Show ID bhejien</b> (jaise <code>1700000084</code> ya <code>1700000196</code>)\n"
        "Ya show ka naam / URL likhein, ya neeche quick button dabayein.\n\n"
        "⚡ Bot <b>pura show ek-ek karke</b> download karke aapke channel par upload karega aur <b>GitHub JSON</b> me backup bhi banayega!</blockquote>\n\n"
        "<i>Send /cancel to abort.</i>"
    )

    text = header + "\n".join(lines) + footer

    buttons = [
        [
            InlineKeyboardButton("🎭 TMKOC (1700000084)", callback_data="sony_pick:1700000084"),
            InlineKeyboardButton("🕵️ CID (1700000196)", callback_data="sony_pick:1700000196")
        ],
        [
            InlineKeyboardButton("🚔 Crime Patrol (1700000108)", callback_data="sony_pick:1700000108"),
            InlineKeyboardButton("🎤 Kapil Sharma (1700000083)", callback_data="sony_pick:1700000083")
        ],
        [
            InlineKeyboardButton("📈 Scam 1992 (1700000292)", callback_data="sony_pick:1700000292"),
            InlineKeyboardButton("🧑‍⚖️ Adaalat (1700000091)", callback_data="sony_pick:1700000091")
        ],
        [
            InlineKeyboardButton("⚔️ Tenali Rama (1700000003)", callback_data="sony_pick:1700000003"),
            InlineKeyboardButton("🧙 Aladdin (1700000001)", callback_data="sony_pick:1700000001")
        ],
        [
            InlineKeyboardButton("🦸 Baalveer (1700000071)", callback_data="sony_pick:1700000071"),
            InlineKeyboardButton("👻 Aahat (1700000144)", callback_data="sony_pick:1700000144")
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="sony_cancel")
        ]
    ]

    return text, InlineKeyboardMarkup(buttons)


# =========================================================================
# ASYNC HIGH-SPEED STREAM DOWNLOADER WITH LIVE PROGRESS & AS MULTIVERSE
# =========================================================================

def resolve_sony_stream(ep_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolves video stream for SonyLIV episode.
    Primary: AS Multiverse endpoint (https://asmultiverse.site/yt-down/stream.php?id={ep_id})
    which bypasses Heroku datacenter 403 Forbidden blocks and provides 1080p full quality.
    Fallback: Direct SonyLIV Akamai token API.
    """
    # 1. Try AS Multiverse first
    try:
        asm_url = f"https://asmultiverse.site/yt-down/stream.php?id={ep_id}"
        req = urllib.request.Request(
            asm_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://asmultiverse.site/",
                "Accept": "*/*"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                body = resp.read(2048).decode("utf-8", errors="replace")
                if "<MPD" in body or "#EXTM3U" in body:
                    logger.info(f"[ASMultiverse] Resolved full 1080p stream for ep {ep_id}")
                    return {
                        "success": True,
                        "source": "asmultiverse",
                        "streamUrl": asm_url
                    }
    except Exception as asm_e:
        logger.debug(f"[ASMultiverse] ep {ep_id} check notice: {asm_e}")

    # 2. Fallback to Direct SonyLIV
    try:
        direct_res = sony.resolve_video_stream(ep_id)
        if direct_res.get("success"):
            hls = direct_res.get("hlsUrl") or direct_res.get("dashUrl")
            if hls:
                logger.info(f"[DirectSonyLIV] Resolved stream for ep {ep_id}")
                return {
                    "success": True,
                    "source": "direct",
                    "streamUrl": hls
                }
    except Exception as dir_e:
        logger.warning(f"[DirectSonyLIV] Stream resolution failed for ep {ep_id}: {dir_e}")

    return None


async def download_sony_stream_with_progress(
    stream_url: str,
    output_path: Path,
    status_message: Message,
    show_title: str,
    season_num: int,
    ep_num: int,
    ep_title: str,
    total_eps_in_season: Any
) -> bool:
    """
    Downloads SonyLIV stream (DASH MPD from AS Multiverse or HLS M3U8)
    with yt-dlp or ffmpeg, updating status message with real-time speed & size.
    """
    if output_path.exists():
        try:
            output_path.unlink()
        except OSError:
            pass

    # 1. Primary: yt-dlp (handles AS Multiverse DASH MPD with separate video+audio multiplexing)
    ytdlp_cmd = [
        "yt-dlp",
        "--no-warnings",
        "--add-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "--add-headers", "Referer: https://asmultiverse.site/",
        "-f", "bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        stream_url
    ]

    logger.info(f"Downloading SonyLIV Ep {ep_num}: {show_title} via yt-dlp -> {output_path.name}")
    start_time = time.time()
    last_update = 0.0

    try:
        proc = await asyncio.create_subprocess_exec(
            *ytdlp_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        while True:
            if proc.returncode is not None:
                break

            now = time.time()
            if now - last_update >= 4.0:
                last_update = now
                current_bytes = output_path.stat().st_size if output_path.exists() else 0
                elapsed = max(0.1, now - start_time)
                speed = current_bytes / elapsed

                try:
                    card_text = (
                        f"🎬 <b>SonyLIV High-Speed 1080p Downloader</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📺 <b>Show:</b> <b>{show_title}</b>\n"
                        f"📌 <b>Season:</b> {season_num} | <b>Episode:</b> {ep_num}/{total_eps_in_season}\n"
                        f"📝 <b>Title:</b> <i>{ep_title[:45]}</i>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📥 <b>Status:</b> <b>Downloading 1080p Stream (AS Multiverse)...</b>\n"
                        f"💾 <b>Downloaded:</b> <code>{hrb(current_bytes)}</code>\n"
                        f"⚡ <b>Speed:</b> <code>{hrb(speed)}/s</code>\n"
                        f"⏱️ <b>Elapsed:</b> <code>{hrt(elapsed)}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🤖 <b>Powered by {CREDIT}</b>"
                    )
                    await status_message.edit_text(card_text, parse_mode=enums.ParseMode.HTML)
                except Exception:
                    pass

            await asyncio.sleep(1.0)

        await proc.wait()
    except Exception as ytdlp_err:
        logger.warning(f"yt-dlp launch notice: {ytdlp_err}")

    if output_path.exists() and output_path.stat().st_size > 1024 * 50:
        return True

    # 2. Fallback: FFmpeg
    ffmpeg_bin = os.environ.get("FFMPEG_PATH") or "ffmpeg"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36\r\nOrigin: https://www.sonyliv.com\r\nReferer: https://www.sonyliv.com/\r\n",
        "-i", stream_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-movflags", "+faststart",
        str(output_path)
    ]

    logger.info(f"Falling back to ffmpeg for SonyLIV Ep {ep_num}: {show_title}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.wait()
    except Exception as e:
        logger.error(f"FFmpeg fallback failed: {e}")

    return output_path.exists() and output_path.stat().st_size > 1024 * 50



# =========================================================================
# TELEGRAM COMMANDS: /sonyliv, /stopsonyliv, /recoversonyliv
# =========================================================================

async def stop_sonyliv_cmd(client: Client, message: Message):
    """Safely pauses/stops ongoing SonyLIV download tasks."""
    global _SONY_STOP_REQUESTED
    _SONY_STOP_REQUESTED = True
    await message.reply_text("🛑 <b>Stopping SonyLIV downloads safely... Finishing current operation.</b>", parse_mode=enums.ParseMode.HTML)


async def recoversonyliv_cmd(client: Client, message: Message):
    """
    Recovers already uploaded SonyLIV episodes by scanning the Telegram channel
    and updating data/shows/sony_{show_id}.json without re-downloading!
    Usage: /recoversonyliv <channel_id> <show_id>
    """
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.reply_text(
            "⚡ <b>SonyLIV Channel Recovery</b>\n\n"
            "<b>Usage:</b> `/recoversonyliv <channel_id> <show_id>`\n"
            "<b>Example:</b> `/recoversonyliv -1002233445566 1700000084`\n\n"
            "<i>Scans channel messages, matches Episode numbers, and updates JSON on GitHub!</i>",
            parse_mode=enums.ParseMode.HTML
        )

    channel_id = int(args[1].strip())
    show_id = args[2].strip()

    status_msg = await message.reply_text(f"🔍 Scanning channel <code>{channel_id}</code> for SonyLIV show <code>{show_id}</code>...")
    sony = DirectSonyLIV()
    try:
        show_details = await asyncio.to_thread(sony.get_show_details, show_id)
        show_title = show_details.get("title", f"Show {show_id}")
    except Exception:
        show_title = f"Show {show_id}"

    show_obj = load_sony_show_json(show_id)
    show_obj["showId"] = show_id
    show_obj["showTitle"] = show_title
    show_obj["channelId"] = str(channel_id)
    show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")

    episodes_map = {int(ep["episodeNumber"]): ep for ep in show_obj.get("episodes", []) if "episodeNumber" in ep}
    recovered_count = 0

    try:
        clean_ch_id = str(channel_id).replace("-100", "")
        async for msg in client.get_chat_history(channel_id, limit=2000):
            if not msg.video:
                continue

            text_block = (msg.caption or "") + " " + (msg.video.file_name or "")
            # Match Episode pattern (e.g. Episode 12, Ep 12, E12)
            m = re.search(r"(?:Episode|Ep|E)[.\s_-]*(\d+)", text_block, re.IGNORECASE)
            if m:
                ep_num = int(m.group(1))
                if ep_num not in episodes_map or not episodes_map[ep_num].get("telegramUrl"):
                    recovered_count += 1
                    episodes_map[ep_num] = {
                        "id": str(msg.id),
                        "episodeNumber": ep_num,
                        "title": f"Episode {ep_num}",
                        "fileSize": msg.video.file_size,
                        "duration": msg.video.duration,
                        "telegramUrl": f"https://t.me/c/{clean_ch_id}/{msg.id}",
                        "telegramMessageId": msg.id,
                        "uploadedAt": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

        show_obj["episodes"] = [episodes_map[k] for k in sorted(episodes_map.keys())]
        pushed = sync_sony_show_to_github(show_id, show_title, show_obj)

        await status_msg.edit_text(
            f"🎉 <b>SonyLIV Channel Recovery Completed!</b>\n\n"
            f"🎬 <b>Show:</b> <b>{show_title}</b> (<code>{show_id}</code>)\n"
            f"📥 <b>Recovered:</b> <b>{recovered_count}</b> new episodes (Total: {len(episodes_map)})\n"
            f"📢 <b>Channel:</b> <code>{channel_id}</code>\n"
            f"🌐 <b>GitHub Sync:</b> {'✅ Synced to GitHub repository' if pushed else '💾 Saved locally in data/shows/'}\n\n"
            f"<i>Now re-running <code>/sonyliv {show_id}</code> will skip these episodes automatically!</i>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        logger.exception("SonyLIV recovery error")
        await status_msg.edit_text(f"❌ Recovery failed: <code>{e}</code>", parse_mode=enums.ParseMode.HTML)


async def sonyliv_cmd(client: Client, message: Message, target_show_id: Optional[str] = None):
    """
    Automated SonyLIV Downloader & Channel Uploader:
    - Usage: /sonyliv <show_id or url or name> [channel_id] (or /sony)
    - If show_id not given, presents popular Sony TV show catalog with 1-click buttons.
    - If channel_id not given, prompts user interactively (or /d for current chat).
    - Fetches all seasons & episodes from SonyLIV API with pagination.
    - Downloads HLS stream, watermarks, extracts thumbnail, uploads to channel sequentially.
    - Syncs episode metadata to data/shows/sony_{show_id}.json & pushes to GitHub.
    - Real-time progress updates on both downloading and uploading.
    """
    global _SONY_STOP_REQUESTED
    _SONY_STOP_REQUESTED = False

    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    args = (message.text or "").split()
    target_channel_id = None

    if not target_show_id and len(args) > 1:
        target_show_id = extract_sony_show_id(" ".join(args[1:])) or extract_sony_show_id(args[1])

    if len(args) > 2 and not target_channel_id:
        ch_arg = args[2].strip()
        if ch_arg.startswith("-100") or ch_arg.startswith("-"):
            target_channel_id = int(ch_arg)
        elif ch_arg.isdigit():
            target_channel_id = int(f"-100{ch_arg}")

    editable = await message.reply_text(
        "🎬 <b>SonyLIV High-Speed 1080p Engine</b>\n\n"
        "<i>Connecting to SonyLIV official stream server...</i>",
        parse_mode=enums.ParseMode.HTML
    )

    sony = DirectSonyLIV()

    # Step 1: Prompt for Show ID if not given (Display Rich Show Catalog & Buttons)
    if not target_show_id:
        catalog_text, catalog_markup = build_sony_catalog_panel()
        await editable.edit_text(catalog_text, reply_markup=catalog_markup, parse_mode=enums.ParseMode.HTML)
        try:
            resp_msg = await client.listen(chat_id=chat_id, user_id=user_id, timeout=180)
            text_in = resp_msg.text.strip()
            try:
                await resp_msg.delete()
            except Exception:
                pass
            if text_in.lower() in ("/cancel", "cancel"):
                return await editable.edit_text("❌ <b>Operation cancelled.</b>", parse_mode=enums.ParseMode.HTML)
            target_show_id = extract_sony_show_id(text_in)
        except Exception:
            return await editable.edit_text("⏱️ <b>Timeout waiting for Show ID.</b>", parse_mode=enums.ParseMode.HTML)

    if not target_show_id:
        return await editable.edit_text("❌ <b>Invalid Show ID or Name. Please select from catalog or send a valid Show ID (e.g. <code>1700000084</code>).</b>", parse_mode=enums.ParseMode.HTML)

    # Step 2: Prompt for Channel ID if not provided
    if not target_channel_id:
        await editable.edit_text(
            "📢 <b>Destination Channel Configuration</b>\n\n"
            "<blockquote>Send your <b>Telegram Channel ID</b> (e.g. <code>-1002233445566</code>)\n"
            "Or send <code>/d</code> to upload directly in this chat.</blockquote>\n\n"
            "<i>(Ensure bot is Admin in the channel with Post Messages permission)</i>",
            parse_mode=enums.ParseMode.HTML
        )
        try:
            ch_msg = await client.listen(chat_id=chat_id, user_id=user_id, timeout=120)
            ch_text = ch_msg.text.strip()
            try:
                await ch_msg.delete()
            except Exception:
                pass
            if ch_text.lower() in ("/cancel", "cancel"):
                return await editable.edit_text("❌ <b>Operation cancelled.</b>", parse_mode=enums.ParseMode.HTML)
            target_channel_id = chat_id if ch_text == "/d" else int(ch_text)
        except Exception:
            return await editable.edit_text("⏱️ <b>Timeout waiting for Channel ID.</b>", parse_mode=enums.ParseMode.HTML)

    # Step 3: Fetch Show details
    try:
        await editable.edit_text(f"🔍 <b>Fetching Show Details from SonyLIV API (ID: <code>{target_show_id}</code>)...</b>", parse_mode=enums.ParseMode.HTML)
        show_info = await asyncio.to_thread(sony.get_show_details, target_show_id)
        show_title = show_info.get("title") or f"Show {target_show_id}"
        seasons = show_info.get("seasons", [])
    except Exception as err:
        logger.exception("Failed to fetch show details")
        return await editable.edit_text(f"❌ <b>Failed to fetch show details:</b> <code>{err}</code>", parse_mode=enums.ParseMode.HTML)

    if not seasons:
        return await editable.edit_text(f"❌ <b>No seasons or episodes found for show: {show_title}</b>", parse_mode=enums.ParseMode.HTML)

    # Step 4: Load existing data for deduplication
    show_obj = load_sony_show_json(target_show_id)
    show_obj["showId"] = target_show_id
    show_obj["showTitle"] = show_title
    show_obj["channelId"] = str(target_channel_id)
    show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")

    episodes_map = {int(ep["episodeNumber"]): ep for ep in show_obj.get("episodes", []) if "episodeNumber" in ep}
    clean_ch_id = str(target_channel_id).replace("-100", "")

    await editable.edit_text(
        f"🚀 <b>SonyLIV Full Show Automation Started!</b>\n\n"
        f"🎬 <b>Show:</b> <b>{show_title}</b>\n"
        f"📚 <b>Seasons:</b> {len(seasons)}\n"
        f"📢 <b>Target Channel:</b> <code>{target_channel_id}</code>\n"
        f"⚡ <b>Fast HLS & Watermark:</b> Active\n"
        f"🌐 <b>GitHub Auto-Sync:</b> Active\n\n"
        f"<i>Send /stopsonyliv anytime to safely pause.</i>",
        parse_mode=enums.ParseMode.HTML
    )

    uploaded_count = 0
    skipped_count = 0

    # Step 5: Iterate through all seasons and episodes sequentially (ek-ek karke)
    for s_idx, season in enumerate(seasons, 1):
        if _SONY_STOP_REQUESTED:
            await message.reply_text("🛑 <b>SonyLIV Batch stopped cleanly upon user request.</b>", parse_mode=enums.ParseMode.HTML)
            break

        season_id = season.get("id")
        season_title = season.get("title") or f"Season {s_idx}"

        try:
            episodes = await asyncio.to_thread(sony.get_all_season_episodes, season_id)
        except Exception as e:
            logger.warning(f"Failed to fetch episodes for season {season_id}: {e}")
            continue

        total_in_season = len(episodes)

        for ep in episodes:
            if _SONY_STOP_REQUESTED:
                break

            ep_num = int(ep.get("episodeNumber", 1))
            ep_id = str(ep.get("id"))
            ep_title = ep.get("title") or f"Episode {ep_num}"
            duration = ep.get("duration")
            thumb_url = ep.get("thumbnail")

            # Deduplication: Check if already uploaded
            if ep_num in episodes_map and episodes_map[ep_num].get("telegramUrl"):
                skipped_count += 1
                continue

            # Resolve video stream (AS Multiverse primary to bypass Heroku 403)
            try:
                stream_res = await asyncio.to_thread(resolve_sony_stream, ep_id)
            except Exception as stream_err:
                logger.warning(f"Failed to resolve stream for ep {ep_id}: {stream_err}")
                stream_res = None

            if not stream_res or not stream_res.get("streamUrl"):
                logger.error(f"[SonyLIV] Ep {ep_id} stream resolution failed. Stopping job immediately.")
                err_text = (
                    f"🛑 <b>SonyLIV Job Stopped on Failure</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>Download stopped immediately upon stream resolution failure.</i>\n\n"
                    f"🎬 <b>Show:</b> <b>{show_title}</b>\n"
                    f"📌 <b>Failed Episode:</b> Episode {ep_num} (<code>{ep_id}</code>)\n"
                    f"📝 <b>Title:</b> {ep_title}\n"
                    f"❌ <b>Error:</b> <code>Unable to resolve stream from AS Multiverse or Direct SonyLIV</code>\n\n"
                    f"📊 <b>Summary:</b>\n"
                    f"• ✅ <b>Uploaded:</b> {uploaded_count}\n"
                    f"• ⏩ <b>Skipped:</b> {skipped_count}\n"
                    f"• ⏳ <b>Pending (Halted):</b> {max(0, total_in_season - ep_num)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 <b>{CREDIT}</b>"
                )
                await editable.edit_text(err_text, parse_mode=enums.ParseMode.HTML)
                _SONY_STOP_REQUESTED = True
                break

            hls_url = stream_res.get("streamUrl")

            # Local temp files
            temp_vid = TEMP_DOWNLOAD_DIR / f"sony_{target_show_id}_s{s_idx}_ep{ep_num}_{int(time.time())}.mp4"
            temp_thumb = TEMP_DOWNLOAD_DIR / f"sony_{target_show_id}_thumb_s{s_idx}_ep{ep_num}.jpg"

            # Download thumbnail
            if thumb_url:
                try:
                    urllib.request.urlretrieve(thumb_url, str(temp_thumb))
                except Exception:
                    pass

            # Download stream with live progress
            download_ok = await download_sony_stream_with_progress(
                stream_url=hls_url,
                output_path=temp_vid,
                status_message=editable,
                show_title=show_title,
                season_num=s_idx,
                ep_num=ep_num,
                ep_title=ep_title,
                total_eps_in_season=total_in_season
            )

            if not download_ok or not temp_vid.exists() or temp_vid.stat().st_size == 0:
                if temp_thumb.exists():
                    try: temp_thumb.unlink()
                    except Exception: pass
                logger.error(f"[SonyLIV] Ep {ep_id} download failed. Stopping job immediately.")
                err_text = (
                    f"🛑 <b>SonyLIV Job Stopped on Failure</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>Download failed and was stopped immediately to prevent consecutive errors.</i>\n\n"
                    f"🎬 <b>Show:</b> <b>{show_title}</b>\n"
                    f"📌 <b>Failed Episode:</b> Episode {ep_num} (<code>{ep_id}</code>)\n"
                    f"📝 <b>Title:</b> {ep_title}\n"
                    f"❌ <b>Error:</b> <code>Stream download produced empty or corrupt file</code>\n\n"
                    f"📊 <b>Summary:</b>\n"
                    f"• ✅ <b>Uploaded:</b> {uploaded_count}\n"
                    f"• ⏩ <b>Skipped:</b> {skipped_count}\n"
                    f"• ⏳ <b>Pending (Halted):</b> {max(0, total_in_season - ep_num)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 <b>{CREDIT}</b>"
                )
                await editable.edit_text(err_text, parse_mode=enums.ParseMode.HTML)
                _SONY_STOP_REQUESTED = True
                break

            # Apply watermark if enabled
            final_vid = str(temp_vid)
            if WATERMARK_TEXT and WATERMARK_TEXT not in ("/d", "no", "none", ""):
                try:
                    wm_res = await asyncio.to_thread(helper.apply_video_watermark, str(temp_vid), WATERMARK_TEXT, WATERMARK_FILE)
                    if wm_res and os.path.exists(wm_res):
                        final_vid = wm_res
                except Exception as wm_e:
                    logger.warning(f"Watermark failed: {wm_e}")

            # Extract fallback thumbnail if remote thumb not available
            thumb_path = str(temp_thumb) if temp_thumb.exists() else None
            if not thumb_path:
                try:
                    extracted_thumb = await asyncio.to_thread(helper.extract_or_download_thumbnail, final_vid, None, None)
                    if extracted_thumb and os.path.exists(extracted_thumb):
                        thumb_path = extracted_thumb
                except Exception:
                    pass

            # Format enriched caption
            caption = (
                f"🎬 <b>{show_title}</b> — Episode {ep_num}\n"
                f"📌 <b>Season:</b> {season_title} | <b>Episode:</b> {ep_num}\n"
                f"📝 <b>Title:</b> {ep_title}\n"
                f"📺 <b>Quality:</b> 1080p Full HD • Akamai CDN\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 <b>Downloaded via:</b> {CREDIT}"
            )

            # Upload to Telegram channel/chat
            try:
                await editable.edit_text(
                    f"📤 <b>Uploading Episode {ep_num}/{total_in_season}...</b>\n"
                    f"🎬 <b>{show_title}</b> ({season_title})\n"
                    f"💾 Size: <code>{hrb(os.path.getsize(final_vid))}</code>",
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                pass

            uploaded_msg = None
            try:
                uploaded_msg = await client.send_video(
                    chat_id=target_channel_id,
                    video=final_vid,
                    caption=caption,
                    thumb=thumb_path,
                    supports_streaming=True,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception as up_err:
                logger.error(f"Failed to upload ep {ep_num}: {up_err}")

            # Clean up temp files immediately post-upload
            if os.path.exists(final_vid):
                try: os.unlink(final_vid)
                except Exception: pass
            if temp_vid.exists():
                try: temp_vid.unlink()
                except Exception: pass
            if temp_thumb.exists():
                try: temp_thumb.unlink()
                except Exception: pass

            if uploaded_msg:
                uploaded_count += 1
                msg_id = uploaded_msg.id
                tg_url = f"https://t.me/c/{clean_ch_id}/{msg_id}" if str(target_channel_id).startswith("-100") else ""

                episodes_map[ep_num] = {
                    "id": ep_id,
                    "episodeNumber": ep_num,
                    "season": s_idx,
                    "title": ep_title,
                    "duration": duration,
                    "fileSize": uploaded_msg.video.file_size if uploaded_msg.video else 0,
                    "telegramUrl": tg_url,
                    "telegramMessageId": msg_id,
                    "uploadedAt": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                # Save JSON and periodically sync to GitHub (every 3 episodes)
                show_obj["episodes"] = [episodes_map[k] for k in sorted(episodes_map.keys())]
                show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if uploaded_count % 3 == 0:
                    await asyncio.to_thread(sync_sony_show_to_github, target_show_id, show_title, show_obj)

    # Final GitHub Sync: ONLY IF AT LEAST ONE EPISODE WAS UPLOADED!
    pushed = False
    if uploaded_count > 0:
        show_obj["episodes"] = [episodes_map[k] for k in sorted(episodes_map.keys())]
        show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        pushed = await asyncio.to_thread(sync_sony_show_to_github, target_show_id, show_title, show_obj)
    else:
        logger.info(f"Skipping GitHub sync for {show_title} because 0 episodes were uploaded.")

    if not _SONY_STOP_REQUESTED:
        await editable.edit_text(
            f"🎉 <b>SonyLIV Batch Completed!</b>\n\n"
            f"🎬 <b>Show:</b> <b>{show_title}</b> (<code>{target_show_id}</code>)\n"
            f"✅ <b>Uploaded in this run:</b> {uploaded_count} episodes\n"
            f"⏩ <b>Skipped (Already in channel):</b> {skipped_count} episodes\n"
            f"📊 <b>Total in JSON Catalog:</b> {len(show_obj['episodes'])} episodes\n"
            f"🌐 <b>GitHub JSON Sync:</b> {'✅ Synced to GitHub repository' if pushed else '💾 Saved locally in data/shows/'}\n"
            f"📢 <b>Destination Channel:</b> <code>{target_channel_id}</code>",
            parse_mode=enums.ParseMode.HTML
        )


async def sonyliv_callback_handler(client: Client, query: CallbackQuery):
    """Handles 1-click show selection buttons from the Sony TV catalog."""
    data = query.data
    if data == "sony_cancel":
        await query.answer("Operation cancelled.")
        try:
            await query.message.edit_text("❌ <b>SonyLIV operation cancelled.</b>", parse_mode=enums.ParseMode.HTML)
        except Exception:
            pass
        return

    if data.startswith("sony_pick:"):
        show_id = data.split(":", 1)[1]
        await query.answer(f"Selected show ID: {show_id}")
        msg = query.message
        msg.from_user = query.from_user
        msg.text = f"/sony {show_id}"
        await sonyliv_cmd(client, msg, target_show_id=show_id)

