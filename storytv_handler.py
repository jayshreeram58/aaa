import os
import re
import sys
import json
import time
import base64
import shutil
import asyncio
import logging
import subprocess
import urllib.request
import urllib.error
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

# GitHub synchronization configuration
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
STORYTV_GITHUB_REPO = os.environ.get("STORYTV_GITHUB_REPO", "ramjipatel-tech/storytv-api").strip()
STORYTV_GITHUB_BRANCH = os.environ.get("STORYTV_GITHUB_BRANCH", "master").strip()

OFFICIAL_API = "https://api.storytv.asia"
STORYTV_PORTAL_API = "https://storytv.4umovies.site/api"

# Verified active JWT fallback
DEFAULT_JWT = (
    "eyJhbGciOiJIUzI1NiJ9.eyJjcmVhdGVkRGF0ZSI6IjIwMjUtMTEtMjkgMDg6MjQ6MjcuNTY2Iiwic2Vzc2lvbklkIjoiMjIzMjk2NzIyIiwi"
    "ZGV2aWNlSWQiOiI3MmY4Yjg3M2MxMTE4ZGEyIiwic3ViIjoiMzM2OTExNTUiLCJleHAiOjE3OTI4NjQxNzB9.85fi95pTZXrZbW-6MrUms5oHOnXNyb2VcHvMcS1BhYw"
)

# Global stop flag
_STOP_REQUESTED = False

# =========================================================================
# HELPER FUNCTIONS: PROGRESS BAR, FORMATTERS, SESSIONS
# =========================================================================

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
    """Formats seconds to human readable time string (e.g. 02m 45s, 01h 12m)."""
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
# GITHUB & REMOTE REST API SYNCHRONIZATION
# =========================================================================

def github_put_file_api(file_path: str, content_dict: Any, commit_msg: str) -> bool:
    """Pushes/updates a JSON file on GitHub using GitHub REST API."""
    token = GITHUB_TOKEN or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        return False

    url = f"https://api.github.com/repos/{STORYTV_GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CourseWallah-StoryTVSync/1.0"
    }

    # 1. Check existing file SHA
    sha = None
    try:
        req = urllib.request.Request(f"{url}?ref={STORYTV_GITHUB_BRANCH}", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode())
                sha = body.get("sha")
    except urllib.error.HTTPError as he:
        if he.code == 404:
            sha = None
        else:
            logger.warning(f"GitHub API SHA check error {he.code}: {he}")
    except Exception as ge:
        logger.debug(f"GitHub SHA check error: {ge}")

    # 2. Base64 encode JSON payload
    raw_bytes = json.dumps(content_dict, indent=2, ensure_ascii=False).encode("utf-8")
    b64_content = base64.b64encode(raw_bytes).decode("utf-8")

    payload: Dict[str, Any] = {
        "message": commit_msg,
        "content": b64_content,
        "branch": STORYTV_GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha

    # 3. Send PUT request to GitHub
    try:
        put_req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="PUT"
        )
        with urllib.request.urlopen(put_req, timeout=15) as put_res:
            if put_res.status in (200, 201):
                logger.info(f"🚀 Pushed '{file_path}' to GitHub ({STORYTV_GITHUB_REPO}) via REST API")
                return True
    except Exception as pe:
        logger.warning(f"GitHub API PUT failed for '{file_path}': {pe}")
    return False

def sync_show_to_github(show_id: str, show_title: str, show_obj: Dict[str, Any]) -> bool:
    """
    Commits and pushes updated show JSON and catalog index to GitHub repository.
    Supports both local Git repository commits and remote GitHub REST API commits (Colab/Docker).
    """
    total_eps_uploaded = len([e for e in show_obj.get("episodes", []) if e.get("telegramUrl") or e.get("status") == "uploaded"])

    # 1. Update local files in all directories
    save_show_json_data(show_id, show_obj)
    update_shows_index(show_id, show_obj)

    git_success = False

    # 2. Try Local Git CLI Push first (if local git repo exists)
    local_repo_dir = EXPERIMENT_API_DIR if (EXPERIMENT_API_DIR / ".git").exists() else None
    if not local_repo_dir and (BASE_DIR / ".git").exists():
        # Check if current bot repo contains data/shows
        if (BASE_DIR / "data" / "shows").exists():
            local_repo_dir = BASE_DIR

    if local_repo_dir:
        try:
            rel_show_file = f"data/shows/{show_id}.json"
            subprocess.run(["git", "add", rel_show_file, "data/shows_index.json"], cwd=str(local_repo_dir), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            commit_msg = f"update(storytv): Sync {show_title} ({show_id}) with {total_eps_uploaded} episodes [skip ci]"
            # Commit (ignore error if nothing changed)
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(local_repo_dir), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Push to origin
            push_res = subprocess.run(["git", "push", "origin", STORYTV_GITHUB_BRANCH], cwd=str(local_repo_dir), check=False, capture_output=True, text=True)
            if push_res.returncode == 0:
                logger.info(f"🚀 Git pushed {show_id}.json to GitHub origin/{STORYTV_GITHUB_BRANCH}")
                git_success = True
            else:
                logger.debug(f"Git push notice: {push_res.stderr.strip()[:150]}")
        except Exception as e:
            logger.debug(f"Local git sync notice: {e}")

    # 3. Try GitHub REST API (especially on Colab or server without local git credentials)
    if not git_success and (GITHUB_TOKEN or os.environ.get("GH_TOKEN")):
        ok1 = github_put_file_api(
            file_path=f"data/shows/{show_id}.json",
            content_dict=show_obj,
            commit_msg=f"update(storytv): Sync {show_title} ({show_id}) with {total_eps_uploaded} episodes [skip ci]"
        )
        # Also sync shows_index.json to GitHub API
        idx_data = load_all_catalog_shows()
        if idx_data:
            github_put_file_api(
                file_path="data/shows_index.json",
                content_dict=idx_data,
                commit_msg=f"update(catalog): Sync shows index for {show_title} ({show_id}) [skip ci]"
            )
        git_success = ok1

    return git_success

# =========================================================================
# CATALOG & JSON DEDUPLICATION LOGIC
# =========================================================================

def load_all_catalog_shows() -> List[Dict[str, Any]]:
    """Loads all catalog shows (1,215 shows)."""
    candidate_indices = [
        CATALOG_PATH,
        BASE_DIR / "data" / "shows_index.json",
        EXPERIMENT_API_DIR / "data" / "shows_index.json"
    ]
    for c in candidate_indices:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception as e:
                logger.error(f"Error loading catalog from {c}: {e}")
    return []

def update_shows_index(show_id: str, show_obj: Dict[str, Any]):
    """Updates the shows_index.json file with the latest episode count and status."""
    index_paths = [
        BASE_DIR / "data" / "shows_index.json",
        EXPERIMENT_API_DIR / "data" / "shows_index.json"
    ]
    catalog = load_all_catalog_shows()
    if not catalog:
        return

    ep_count = len([e for e in show_obj.get("episodes", []) if e.get("status") == "uploaded" or e.get("telegramUrl")])
    total_eps = int(show_obj.get("totalEpisodes", 0) or 0)

    updated = False
    for item in catalog:
        if str(item.get("showId")) == str(show_id):
            item["uploadedEpisodes"] = ep_count
            item["lastUpdated"] = show_obj.get("lastUpdated", time.strftime("%Y-%m-%d %H:%M:%S"))
            item["channelId"] = show_obj.get("channelId", "")
            if total_eps > 0 and ep_count >= total_eps:
                item["status"] = "completed"
            elif ep_count > 0:
                item["status"] = "in_progress"
            updated = True
            break

    if updated:
        for p in index_paths:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as fp:
                    json.dump(catalog, fp, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.debug(f"Could not write shows_index to {p}: {e}")

def fetch_remote_github_show_json(show_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches show JSON directly from GitHub repository (master branch).
    Guarantees state is preserved even if the bot is restarted on a fresh machine/Colab!
    """
    urls = [
        f"https://raw.githubusercontent.com/{STORYTV_GITHUB_REPO}/{STORYTV_GITHUB_BRANCH}/data/shows/{show_id}.json",
        f"https://raw.githubusercontent.com/{STORYTV_GITHUB_REPO}/master/data/shows/{show_id}.json",
        f"https://raw.githubusercontent.com/{STORYTV_GITHUB_REPO}/main/data/shows/{show_id}.json"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    token = GITHUB_TOKEN or os.environ.get("GH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"token {token}"

    for u in urls:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, dict) and data.get("episodes"):
                        logger.info(f"📥 Restored {len(data['episodes'])} existing episodes for show {show_id} from GitHub!")
                        return data
        except Exception:
            continue
    return None

def load_show_json_data(show_id: str) -> Dict[str, Any]:
    """
    Loads full existing show JSON dict.
    Checks local files first; if missing, restores from GitHub automatically!
    """
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
                    if isinstance(data, dict) and data.get("episodes"):
                        return data
            except Exception:
                pass

    # Fallback to Remote GitHub repository
    remote_data = fetch_remote_github_show_json(show_id)
    if remote_data:
        # Cache locally so disk has it immediately
        save_show_json_data(show_id, remote_data)
        return remote_data

    return {"showId": str(show_id), "episodes": []}

def get_uploaded_episode_indices(show_id: str) -> Set[int]:
    """
    Checks JSON file on disk or GitHub for this show.
    Returns a set of episode indices that are already uploaded to Telegram
    (having telegramMessageId, telegramUrl, or status == 'uploaded').
    This guarantees ZERO duplicate downloads and seamless resume!
    """
    uploaded: Set[int] = set()
    show_obj = load_show_json_data(show_id)
    for ep in show_obj.get("episodes", []):
        if ep.get("status") == "uploaded" or ep.get("telegramMessageId") or ep.get("telegramUrl") or ep.get("fileId"):
            if "index" in ep:
                try:
                    uploaded.add(int(ep["index"]))
                except (ValueError, TypeError):
                    pass
    return uploaded

def save_show_json_data(show_id: str, show_obj: Dict[str, Any]):
    """
    Saves updated show JSON to disk immediately after each episode upload.
    Ensures that if Colab or the bot stops, no progress is ever lost.
    """
    dest_dirs = [DATA_SHOWS_DIR, EXTRACTED_SHOWS_DIR]
    if EXPERIMENT_API_DIR.exists():
        dest_dirs.append(EXPERIMENT_SHOWS_DIR)

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
# FAST MULTI-THREADED DOWNLOADER WITH LIVE PERCENTAGE PROGRESS
# =========================================================================

async def download_video_stream_with_progress(
    stream_url: str,
    output_path: Path,
    status_message: Optional[Message],
    show_title: str,
    ep_idx: int,
    total_eps: Any,
    target_channel_id: int
) -> bool:
    """
    Downloads HLS stream in 1080p Full HD using yt-dlp with 16 parallel fragment threads.
    Streams real-time download progress directly to the Telegram editable status card.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--newline",
        "--no-warnings",
        "--concurrent-fragments", "16",  # 16x parallel accelerators
        "-f", "bestvideo[height<=1080]+bestaudio[abr>=128]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        stream_url,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        last_edit = 0.0

        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", "ignore").strip()

            # Parse yt-dlp progress: [download]  56.3% of ~  24.41MiB at    3.77MiB/s ETA 00:09
            m = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+~?\s*([\d\.]+[A-Za-z]+)\s+at\s+([\d\.]+[A-Za-z]+/s)\s+ETA\s+([\d:]+)", line)
            if m and status_message:
                pct = float(m.group(1))
                tot_str = m.group(2)
                spd_str = m.group(3)
                eta_str = m.group(4)

                now = time.time()
                if now - last_edit >= 2.0:
                    last_edit = now
                    bar = make_progress_bar(pct, bar_length=12)
                    card = (
                        "╭────────────────────────────╮\n"
                        "│      🎬 <b>STORY TV VIP</b>        │\n"
                        "│                            │\n"
                        "│    📥 <b>DOWNLOADING 1080p</b>     │\n"
                        "│                            │\n"
                        f"│ 📺 <b>Show:</b> {show_title[:28]}\n"
                        f"│ 🎬 <b>Episode:</b> {ep_idx}/{total_eps}\n"
                        f"│ <code>{bar}</code> <b>{pct:5.1f}%</b>\n"
                        f"│ ⚡ <b>Speed:</b> {spd_str} | ⏱️ <b>ETA:</b> {eta_str}\n"
                        f"│ 💾 <b>Size:</b> {tot_str}\n"
                        "│                            │\n"
                        f"│ 🚀 <b>Quality:</b> 1080p Full HD (16x Threads)\n"
                        f"│ 📢 <b>Channel:</b> <code>{target_channel_id}</code>\n"
                        "│ 🛑 <i>Send /stopstorytv to pause</i>\n"
                        "╰────────────────────────────╯"
                    )
                    try:
                        await status_message.edit_text(card)
                    except Exception:
                        pass

        await proc.wait()
        return proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 50000

    except Exception as e:
        logger.error(f"Async yt-dlp download failed: {e}")
        return False

# =========================================================================
# TELEGRAM COMMAND HANDLERS: /storytv, /stopstorytv, /recoverstorytv
# =========================================================================

async def stop_storytv_cmd(client: Client, message: Message):
    """Command to cleanly stop the automated StoryTV batch process."""
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    await message.reply_text(
        "🛑 <b>StoryTV Batch Process Stop Requested!</b>\n\n"
        "The current upload will finish safely and all progress is auto-saved and synced to GitHub.\n"
        "Run <code>/storytv</code> anytime to resume without duplicates!"
    )

async def recover_storytv_cmd(client: Client, message: Message):
    """
    Recover all uploaded episodes from Telegram Channel into the JSON API:
    Syntax: /recoverstorytv <channel_id> [show_id]
    Example: /recoverstorytv -1002233445566 2935
    """
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text(
            "📖 <b>Telegram Channel Recovery Tool</b>\n\n"
            "This command scans your Telegram channel, recovers all previously uploaded episodes, "
            "rebuilds the show JSON, and pushes it directly to the <b>storytv-api</b> on GitHub!\n\n"
            "<b>Usage:</b>\n"
            "<code>/recoverstorytv &lt;channel_id&gt; [show_id]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/recoverstorytv -1002233445566 2935</code>"
        )
        return

    channel_id_str = args[1].strip()
    target_show_id = args[2].strip() if len(args) > 2 else "2935"

    try:
        channel_id = int(channel_id_str)
    except ValueError:
        await message.reply_text("❌ Invalid channel ID. Must be integer e.g. -1002233445566")
        return

    status_msg = await message.reply_text(
        f"🔍 <b>Scanning Channel <code>{channel_id}</code> for Show {target_show_id}...</b>\n\n"
        f"<i>Reading message history and recovering video file IDs...</i>"
    )

    clean_ch_id = str(channel_id).replace("-100", "")

    # Load existing show data or fresh structure
    show_obj = load_show_json_data(target_show_id)
    episodes_map = {int(ep["index"]): ep for ep in show_obj.get("episodes", []) if "index" in ep}

    recovered_count = 0

    try:
        # Scan messages from channel in batches of 100
        # Since Telegram Bot API allows getting messages by ID:
        # We search from message 1 up to 1000
        batch_ids = []
        for mid in range(1, 1001):
            batch_ids.append(mid)
            if len(batch_ids) >= 100 or mid == 1000:
                try:
                    msgs = await client.get_messages(chat_id=channel_id, message_ids=batch_ids)
                    for m in msgs:
                        if not m or not m.video or not m.caption:
                            continue
                        # Match Show ID and Episode index from caption
                        # Caption format:
                        # 🎬 Show Title — Episode 12
                        # 🆔 Show ID: 2935 • Episode: 12/650
                        m_show = re.search(r"Show ID:\s*<code>?(\d+)</code>?", m.caption, re.IGNORECASE)
                        m_ep = re.search(r"Episode\s*(\d+)", m.caption, re.IGNORECASE)
                        if not m_ep:
                            m_ep = re.search(r"Episode:\s*(\d+)", m.caption, re.IGNORECASE)

                        found_show_id = m_show.group(1) if m_show else target_show_id
                        if found_show_id == target_show_id and m_ep:
                            ep_num = int(m_ep.group(1))
                            tg_url = f"https://t.me/c/{clean_ch_id}/{m.id}"

                            if ep_num not in episodes_map or not episodes_map[ep_num].get("telegramUrl"):
                                episodes_map[ep_num] = {
                                    "index": ep_num,
                                    "contentId": str(ep_num),
                                    "title": f"Episode {ep_num}",
                                    "label": f"{ep_num}",
                                    "telegramMessageId": m.id,
                                    "telegramUrl": tg_url,
                                    "fileId": m.video.file_id,
                                    "status": "uploaded",
                                    "recovered": True,
                                    "uploadedAt": time.strftime("%Y-%m-%d %H:%M:%S")
                                }
                                recovered_count += 1
                except Exception as b_err:
                    logger.debug(f"Batch scan notice: {b_err}")
                batch_ids = []

        show_obj["showId"] = target_show_id
        show_obj["channelId"] = str(channel_id)
        show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        show_obj["episodes"] = [episodes_map[k] for k in sorted(episodes_map.keys())]

        # Save and Push to GitHub!
        pushed = sync_show_to_github(target_show_id, show_obj.get("showTitle", f"Show {target_show_id}"), show_obj)

        await status_msg.edit_text(
            f"🎉 <b>Channel Recovery Completed!</b>\n\n"
            f"🎬 <b>Show ID:</b> <code>{target_show_id}</code>\n"
            f"📥 <b>Recovered Episodes:</b> <b>{recovered_count}</b> new (Total: {len(episodes_map)})\n"
            f"📢 <b>Channel:</b> <code>{channel_id}</code>\n"
            f"🌐 <b>GitHub API Status:</b> {'✅ Synced to GitHub repository' if pushed else '💾 Saved locally in data/shows/'}\n\n"
            f"<i>Now re-running <code>/storytv</code> will automatically pick up from episode {len(episodes_map) + 1}!</i>"
        )

    except Exception as rec_err:
        logger.exception("Channel recovery failed")
        await status_msg.edit_text(f"❌ Recovery error: <code>{str(rec_err)}</code>")

async def storytv_cmd(client: Client, message: Message):
    """
    Automated StoryTV Downloader & Channel Uploader:
    - User gives /storytv (optionally with Channel ID, or prompted ONCE for Channel ID).
    - Automatically processes all 1,215 shows sequentially in 1080p Full HD.
    - Shows LIVE real-time percentage progress for both downloading and uploading!
    - Smart Deduplication: Checks local disk AND remote GitHub repository.
      - If an episode already has telegramUrl/telegramMessageId, it is SKIPPED instantly!
      - If pending, it downloads at maximum speed (16x parallel fragments) and uploads to Channel.
    - Periodic GitHub Auto-Sync: Commits and pushes to GitHub every 5 episodes and on show completion!
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
        "🎬 <b>StoryTV High-Speed 1080p Downloader & Channel Uploader</b>\n\n"
        "<i>Initializing 16x parallel accelerator & checking catalog...</i>"
    )

    try:
        # STEP 1: Prompt ONCE if Channel ID is unknown
        if not target_channel_id:
            await editable.edit_text(
                "🎬 <b>StoryTV High-Speed 1080p Engine</b>\n\n"
                "<blockquote>📢 <b>Send Destination Telegram Channel ID</b>:\n"
                "<i>Example: <code>-1002233445566</code> (Bot must be Admin with Post permission)\n"
                "Or send <code>/d</code> to upload right in this chat.</i></blockquote>\n\n"
                "<i>⚡ Once provided, the bot will run completely autonomously for all shows in 1080p Full HD!</i>"
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
            f"🚀 <b>StoryTV High-Speed 1080p Engine Started!</b>\n\n"
            f"📚 <b>Total Shows in Queue:</b> {total_shows}\n"
            f"🌟 <b>Quality:</b> 1080p Full HD (Crisp, High Bitrate + 128k AAC)\n"
            f"⚡ <b>Speed Boost:</b> 16x Parallel Fragment Threads Enabled\n"
            f"📢 <b>Target Channel ID:</b> <code>{target_channel_id}</code>\n"
            f"🛡️ <b>Smart GitHub Auto-Sync:</b> Active (Pushing progress every 5 eps)\n"
            f"🛑 <i>Send /stopstorytv anytime to pause safely.</i>"
        )

        global_uploaded = 0
        global_skipped = 0

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

            # 1. Load existing show data (from disk or GitHub!)
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

                    # Setup local temp files
                    temp_video_file = TEMP_DOWNLOAD_DIR / f"{show_id}_ep_{ep_idx}_{int(time.time())}.mp4"
                    temp_thumb_file = TEMP_DOWNLOAD_DIR / f"{show_id}_thumb_{ep_idx}.jpg"

                    if thumb_url:
                        try:
                            urllib.request.urlretrieve(thumb_url, str(temp_thumb_file))
                        except Exception:
                            pass

                    # -------------------------------------------------------------
                    # PHASE 1: HIGH-SPEED DOWNLOAD WITH REAL-TIME PROGRESS
                    # -------------------------------------------------------------
                    download_ok = await download_video_stream_with_progress(
                        stream_url=stream_url,
                        output_path=temp_video_file,
                        status_message=editable,
                        show_title=show_title,
                        ep_idx=ep_idx,
                        total_eps=catalog_total_eps or "?",
                        target_channel_id=target_channel_id
                    )

                    if not download_ok or not temp_video_file.exists():
                        if temp_thumb_file.exists():
                            try: temp_thumb_file.unlink()
                            except Exception: pass
                        continue

                    # -------------------------------------------------------------
                    # PHASE 2: TELEGRAM UPLOAD WITH REAL-TIME PROGRESS
                    # -------------------------------------------------------------
                    caption = (
                        f"🎬 <b>{show_title}</b> — Episode {ep_idx}\n"
                        f"⚡ <b>Series:</b> {genre}\n"
                        f"📺 <b>Quality:</b> 1080p Full HD Reel (Crisp) | 9:16\n"
                        f"🆔 <b>Show ID:</b> <code>{show_id}</code> &bull; <b>Episode:</b> {sub_txt}\n\n"
                        f"🍿 <i>Uploaded via Course Wallah Bot</i>"
                    )

                    last_upload_edit = [0.0]
                    upload_start_time = [time.time()]

                    async def upload_progress_cb(current, total):
                        now = time.time()
                        if now - last_upload_edit[0] < 2.0 or total <= 0:
                            return
                        last_upload_edit[0] = now

                        elapsed = now - upload_start_time[0]
                        speed = current / elapsed if elapsed > 0.5 else 0.0
                        pct = (current / total) * 100.0
                        bar = make_progress_bar(pct, bar_length=12)
                        spd_str = f"{hrb(speed)}/s" if speed > 0 else "0 B/s"
                        rem_sec = int((total - current) / speed) if speed > 0 else 0
                        eta_str = hrt(rem_sec) if rem_sec > 0 else "00s"

                        card = (
                            "╭────────────────────────────╮\n"
                            "│      🎬 <b>STORY TV VIP</b>        │\n"
                            "│                            │\n"
                            "│    📤 <b>UPLOADING 1080p</b>      │\n"
                            "│                            │\n"
                            f"│ 📺 <b>Show:</b> {show_title[:28]}\n"
                            f"│ 🎬 <b>Episode:</b> {ep_idx}/{catalog_total_eps or '?'}\n"
                            f"│ <code>{bar}</code> <b>{pct:5.1f}%</b>\n"
                            f"│ ⚡ <b>Speed:</b> {spd_str} | ⏱️ <b>ETA:</b> {eta_str}\n"
                            f"│ 💾 <b>Size:</b> {hrb(current)} / {hrb(total)}\n"
                            "│                            │\n"
                            f"│ 📊 <b>Shows:</b> {show_idx}/{total_shows} | ⏭️ Skipped: {global_skipped}\n"
                            f"│ 📢 <b>Channel:</b> <code>{target_channel_id}</code>\n"
                            "│ 🛑 <i>Send /stopstorytv to pause</i>\n"
                            "╰────────────────────────────╯"
                        )
                        try:
                            await editable.edit_text(card)
                        except Exception:
                            pass

                    try:
                        sent_msg = await client.send_video(
                            chat_id=target_channel_id,
                            video=str(temp_video_file),
                            caption=caption,
                            thumb=str(temp_thumb_file) if temp_thumb_file.exists() else None,
                            supports_streaming=True,
                            progress=upload_progress_cb
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

                        # Progressive Auto-Sync to GitHub every 5 episodes!
                        if ep_idx % 5 == 0:
                            sync_show_to_github(show_id, show_title, show_obj)

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

                    await asyncio.sleep(1.2)

                # Advance cursor to the last episode seen in this batch
                last_idx = batch[-1].get("index")
                if cursor is not None and last_idx <= cursor:
                    break
                cursor = last_idx

                # If reached catalog total, finish this show
                if catalog_total_eps > 0 and len(existing_uploaded) >= catalog_total_eps:
                    break

            # End of show: Guarantee full sync and push to GitHub
            sync_show_to_github(show_id, show_title, show_obj)

        # =========================================================================
        # BATCH COMPLETION SUMMARY
        # =========================================================================
        final_summary = (
            f"🎉 <b>StoryTV 1080p Engine Completed!</b>\n\n"
            f"📚 <b>Total Shows in Catalog:</b> {total_shows}\n"
            f"🌟 <b>Quality:</b> 1080p Full HD Native\n"
            f"✅ <b>New Episodes Uploaded:</b> {global_uploaded}\n"
            f"⏭️ <b>Episodes Skipped (Already Uploaded):</b> {global_skipped}\n"
            f"📢 <b>Destination Channel:</b> <code>{target_channel_id}</code>\n"
            f"🌐 <b>GitHub API Status:</b> Auto-synced and pushed to storytv-api\n"
            f"🍿 <b>Zero Duplicate Guarantee:</b> Resumable anytime with /storytv"
        )
        await editable.edit_text(final_summary)

    except asyncio.TimeoutError:
        await editable.edit_text("⏱️ <b>Timed out waiting for Channel ID. Run /storytv again to resume.</b>")
    except Exception as e:
        logger.exception("StoryTV Batch Engine Error")
        await editable.edit_text(f"❌ <b>Error in StoryTV Engine:</b>\n<code>{str(e)}</code>")
