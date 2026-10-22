import os
import re
from os import environ
from typing import Optional, List, Dict, Any, Union
from dotenv import load_dotenv

# Load .env file at the earliest entry point
load_dotenv()

# ==============================================================================
# 🔑 TELEGRAM & BOT CREDENTIALS
# ==============================================================================
API_ID_RAW = os.environ.get("API_ID", "").strip().strip("'\"")
API_ID = int(API_ID_RAW) if API_ID_RAW.isdigit() else 0

API_HASH = os.environ.get("API_HASH", "").strip().strip("'\"")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip().strip("'\"")

BOT_NAME = os.environ.get("BOT_NAME", "Course Wallah Downloader").strip().strip("'\"")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "downloader_course_wallah_bot").strip().strip("'\"")
BOT_LINK = os.environ.get("BOT_LINK", f"https://t.me/{BOT_USERNAME}").strip().strip("'\"")
SUPPORT_LINK = os.environ.get("SUPPORT_LINK", f"https://t.me/{BOT_USERNAME}").strip().strip("'\"")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", BOT_USERNAME).strip().strip("'\"")
SUPPORT_CHAT = os.environ.get("SUPPORT_CHAT", "").strip().strip("'\"")

CREDIT = os.environ.get(
    "CREDIT",
    f'<a href="{BOT_LINK}">𝄟⃝⚡️ 🅲🅾🆄🆁🆂🅴 🆆🅰🅻🅻🅰🅷 💻 𝄟⃝🎓 🔥</a>'
)

# ==============================================================================
# 🤖 MULTI-BOT CENTRAL CONFIGURATION
# ==============================================================================
def get_configured_bots() -> List[Dict[str, Any]]:
    """
    Dynamically loads all configured Telegram bots from environment variables.
    Supports BOT_1_TOKEN, BOT_2_TOKEN, BOT_3_TOKEN, ... BOT_N_TOKEN (dynamic, at least 10+).
    Guarantees unique Pyrogram session names per bot instance and avoids starting duplicate tokens.
    """
    configured = []
    seen_sessions = set()
    seen_tokens = set()

    # Collect all configured bot indices from environment (dynamic scanning)
    indices = set(range(1, 11))
    for k in os.environ.keys():
        m = re.match(r"^BOT_(\d+)_TOKEN$", k)
        if m:
            indices.add(int(m.group(1)))

    for i in sorted(indices):
        token = os.environ.get(f"BOT_{i}_TOKEN", "").strip().strip("'\"")
        # Fallback for bot 1 to legacy BOT_TOKEN if BOT_1_TOKEN is not set
        if i == 1 and not token:
            token = os.environ.get("BOT_TOKEN", "").strip().strip("'\"")

        # Skip empty or placeholder tokens
        if not token or token.lower() in ("your_telegram_bot_token_here", "none", "null", "") or " " in token:
            continue

        # Prevent duplicate tokens (do not start the same bot twice)
        if token in seen_tokens:
            continue
        seen_tokens.add(token)

        b_name = os.environ.get(f"BOT_{i}_NAME", f"coursewallah_{i}" if i > 1 else BOT_NAME).strip().strip("'\"")
        session = os.environ.get(f"BOT_{i}_SESSION", f"coursewallah_bot_{i}").strip().strip("'\"")
        if not session:
            session = f"coursewallah_bot_{i}"

        # Prevent duplicate session names (SQLite lock prevention)
        base_session = session
        dedup_idx = 1
        while session in seen_sessions:
            session = f"{base_session}_{dedup_idx}"
            dedup_idx += 1
        seen_sessions.add(session)

        forum_chat = os.environ.get(f"BOT_{i}_FORUM_CHAT_ID", os.environ.get("FORUM_CHAT_ID", "")).strip().strip("'\"")

        configured.append({
            "id": f"bot_{i}",
            "index": i,
            "name": b_name,
            "token": token,
            "session_name": session,
            "forum_chat_id": forum_chat
        })

    return configured

BOTS: List[Dict[str, Any]] = get_configured_bots()

# ==============================================================================
# 👥 OWNER & ADMINS
# ==============================================================================
MASTER_ADMIN_IDS = [8504838657, 8738736556, 6363840742]

OWNER_ID_RAW = os.environ.get("OWNER_ID", "").strip().strip("'\"")
owner_digits = re.findall(r"\d+", OWNER_ID_RAW)
OWNER_ID = int(owner_digits[0]) if owner_digits else 8504838657

ADMINS_RAW = os.environ.get("ADMINS", "").strip().strip("'\"")
admin_digits = re.findall(r"\d+", ADMINS_RAW)
ADMINS = [int(x) for x in admin_digits]

# Ensure OWNER_ID and master admin IDs are always present
for _aid in [OWNER_ID] + MASTER_ADMIN_IDS:
    if _aid and _aid not in ADMINS:
        ADMINS.append(_aid)

from pathlib import Path
from storage import get_storage_manager, APP_ROOT

# Absolute Project Root
PROJECT_ROOT = APP_ROOT

# ==============================================================================
# 📂 DIRECTORY STRUCTURE (Zero Database Persistence, Centralized Storage)
# ==============================================================================
storage = get_storage_manager()

DATA_DIR = str(storage.get_root_dir())
USERS_DIR = str(storage.get_dir("users"))
JOBS_DIR = str(storage.get_dir("jobs"))
STATE_DIR = str(storage.get_dir("state"))
COOKIES_DIR = str(storage.get_dir("cookies"))
LOGS_DIR = str(storage.get_dir("logs"))
TEMP_DIR = str(storage.get_dir("temp"))
DOWNLOADS_DIR = str(storage.get_dir("downloads"))
OUTPUT_DIR = str(storage.get_dir("output"))
SESSIONS_DIR = str(storage.get_dir("sessions"))
THUMBNAILS_DIR = str(storage.get_dir("thumbnails"))
CACHE_DIR = str(storage.get_dir("cache"))
CONFIG_DIR = str(storage.get_dir("config"))
TOPICS_DIR = str(storage.get_dir("topics"))

# Asset directories
ASSETS_DIR = os.environ.get("ASSETS_DIR", str(PROJECT_ROOT / "assets"))
START_IMAGE_DIR = os.path.join(ASSETS_DIR, "start")
START_IMAGE_PATH = os.environ.get("START_IMAGE_PATH", os.path.join(START_IMAGE_DIR, "start.jpg"))

# Persistent session config
SESSION_NAME = os.environ.get("SESSION_NAME", "bot_session")
SESSION_DIR = SESSIONS_DIR if os.path.exists(SESSIONS_DIR) else STATE_DIR

# State files
USERS_STATE_FILE = os.path.join(STATE_DIR, "users.json")
JOBS_STATE_FILE = os.path.join(STATE_DIR, "jobs.json")
CONFIG_STATE_FILE = os.path.join(STATE_DIR, "config.json")
TOPICS_STATE_FILE = os.path.join(STATE_DIR, "topics.json")

# Ensure all essential directories exist safely
for d in [DATA_DIR, USERS_DIR, JOBS_DIR, STATE_DIR, COOKIES_DIR, LOGS_DIR, TEMP_DIR, DOWNLOADS_DIR, OUTPUT_DIR, SESSIONS_DIR, THUMBNAILS_DIR, CACHE_DIR, CONFIG_DIR, TOPICS_DIR, ASSETS_DIR, START_IMAGE_DIR]:
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass

# Legacy / Global compatibility
DATABASE_ENABLED = False  # Local JSON persistence is always active
DATABASE_NAME = "botdb"
DATABASE_URL = ""
MONGO_URL = ""

# ==============================================================================
# ⚡ CONCURRENCY & WORKER LIMITS
# ==============================================================================
DOWNLOAD_WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "4"))
UPLOAD_WORKERS = int(os.environ.get("UPLOAD_WORKERS", "3"))
MAX_ACTIVE_USERS = int(os.environ.get("MAX_ACTIVE_USERS", "6"))
MAX_JOBS_PER_USER = int(os.environ.get("MAX_JOBS_PER_USER", "1"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "5"))
SPAYEE_SEGMENT_WORKERS = int(os.environ.get("SPAYEE_SEGMENT_WORKERS", "16"))

# ==============================================================================
# 📦 UPLOAD THRESHOLD & VIDEO SPLITTING (Telegram Limit Safety Margin)
# ==============================================================================
# 1950 MB safe threshold to account for Telegram 2000 MB limit & container headers
MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(1950 * 1024 * 1024)))

# ==============================================================================
# 🎨 WATERMARK & BRANDING
# ==============================================================================
WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "Course Wallah")
WATERMARK_FILE = os.environ.get("WATERMARK_FILE", "Course Wallah")
WATERMARK_CRF = int(os.environ.get("WATERMARK_CRF", "26"))

# Default thumbnails
THUMBNAILS = list(map(str, os.environ.get("THUMBNAILS", "").split()))

# Cookies
COOKIES_FILE = os.environ.get("COOKIES_FILE", "cookies.txt")

# ==============================================================================
# 📢 TELEGRAM FORUM / SUPERGROUP SETTINGS
# ==============================================================================
FORUM_CHAT_ID = os.environ.get("FORUM_CHAT_ID", "")
RECORDED_TOPIC_ID = int(os.environ.get("RECORDED_TOPIC_ID", "0")) if os.environ.get("RECORDED_TOPIC_ID", "0").isdigit() else None
LIVE_TOPIC_ID = int(os.environ.get("LIVE_TOPIC_ID", "0")) if os.environ.get("LIVE_TOPIC_ID", "0").isdigit() else None
PREMIUM_CHANNEL = os.environ.get("PREMIUM_CHANNEL", "")
BOT_STATUS_CHAT_ID = os.environ.get("BOT_STATUS_CHAT_ID", "").strip().strip("'\"")

# ==============================================================================
# 🐙 GITHUB AUTOMATION & DATA REPOSITORY SYNC
# ==============================================================================
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", "")).strip().strip("'\"")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "ramjipatel-tech/course-wallah-platform").strip().strip("'\"")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip().strip("'\"")

# ==============================================================================
# 🔧 TOOLS & BINARIES (FFmpeg & Heroku Shared Library Auto-Resolver)
# ==============================================================================

def _configure_linux_library_paths():
    """
    Configures LD_LIBRARY_PATH and PATH on Linux / Heroku environments.
    Dynamically discovers all .so directories under /app/.apt to fix
    Ubuntu shared library errors like:
    'error while loading shared libraries: libpulsecommon-16.1.so'
    """
    import sys
    if sys.platform != "win32":
        all_lib_dirs = [
            "/app/vendor/ffmpeg/bin",
            "/app/.apt/usr/lib/x86_64-linux-gnu/pulseaudio",
            "/app/.apt/usr/lib/x86_64-linux-gnu",
            "/app/.apt/usr/lib",
            "/app/.apt/lib/x86_64-linux-gnu",
            "/app/.apt/lib",
            "/usr/lib/x86_64-linux-gnu/pulseaudio",
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib"
        ]
        # Recursively scan /app/.apt for any directories containing shared libraries (.so)
        if os.path.exists("/app/.apt"):
            for root, dirs, files in os.walk("/app/.apt"):
                if any(f.endswith(".so") or ".so." in f for f in files):
                    if root not in all_lib_dirs:
                        all_lib_dirs.append(root)

        cur_ld = os.environ.get("LD_LIBRARY_PATH", "")
        valid_dirs = [d for d in all_lib_dirs if os.path.isdir(d)]
        if valid_dirs:
            os.environ["LD_LIBRARY_PATH"] = ":".join(valid_dirs) + (f":{cur_ld}" if cur_ld else "")

        # Also ensure static /app/vendor/ffmpeg/bin, /app/data/bin and /app/.apt/usr/bin are in PATH
        bin_dirs = [
            "/app/vendor/ffmpeg/bin",
            "/app/data/bin",
            "/app/.apt/usr/bin",
            "/app/.apt/bin"
        ]
        cur_path = os.environ.get("PATH", "")
        valid_bins = [b for b in bin_dirs if os.path.isdir(b)]
        if valid_bins:
            os.environ["PATH"] = ":".join(valid_bins) + (f":{cur_path}" if cur_path else "")

_configure_linux_library_paths()


def _can_run(binary_path: str) -> bool:
    """Verifies that a binary runs and does not fail with library/missing .so errors."""
    import subprocess
    try:
        r = subprocess.run([binary_path, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4, env=os.environ.copy())
        return r.returncode == 0
    except Exception:
        return False


def _ensure_static_binary(name: str) -> str:
    """Downloads a self-contained static Linux binary if system/apt version is broken or missing."""
    import sys, urllib.request, stat
    if sys.platform == "win32" or name != "ffmpeg":
        return ""
    target_dir = os.path.join(DATA_DIR, "bin")
    os.makedirs(target_dir, exist_ok=True)
    target_bin = os.path.join(target_dir, "ffmpeg")
    if os.path.isfile(target_bin) and _can_run(target_bin):
        return target_bin

    url = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-linux-x64"
    try:
        logger.info(f"Downloading static {name} fallback to {target_bin}...")
        urllib.request.urlretrieve(url, target_bin)
        st = os.stat(target_bin)
        os.chmod(target_bin, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        if _can_run(target_bin):
            logger.info(f"Static {name} downloaded and verified successfully.")
            return target_bin
    except Exception as e:
        logger.warning(f"Failed to auto-download static {name}: {e}")
    return ""


def _find_binary(name: str, env_var: str) -> str:
    """
    Finds a working system binary (ffmpeg / ffprobe) in order:
    1. Explicit env var (FFMPEG_PATH / FFPROBE_PATH)
    2. Heroku static vendor buildpack (/app/vendor/ffmpeg/bin/<name>)
    3. Standalone downloaded binary (/app/data/bin/<name>)
    4. Standard system paths (/usr/bin, /usr/local/bin)
    5. PATH lookup
    6. Heroku Aptfile path (/app/.apt/usr/bin/<name>)
    7. Dynamic static binary download fallback
    """
    import shutil as _shutil

    # 1. Explicit env override
    explicit = os.environ.get(env_var, "").strip().strip("'\"")
    if explicit and os.path.isfile(explicit) and _can_run(explicit):
        return explicit

    # 2. Heroku static vendor buildpack (preferred — zero shared library dependencies)
    vendor_candidate = f"/app/vendor/ffmpeg/bin/{name}"
    if os.path.isfile(vendor_candidate) and _can_run(vendor_candidate):
        return vendor_candidate

    # 3. Standalone verified binary in data directory
    data_bin = os.path.join(DATA_DIR, "bin", name)
    if os.path.isfile(data_bin) and _can_run(data_bin):
        return data_bin

    # 4. Common system paths
    for candidate in [f"/usr/bin/{name}", f"/usr/local/bin/{name}", f"/bin/{name}"]:
        if os.path.isfile(candidate) and _can_run(candidate):
            return candidate

    # 5. PATH lookup
    found = _shutil.which(name)
    if found and _can_run(found):
        return found

    # 6. Heroku apt locations (with discovered LD_LIBRARY_PATH configured)
    for apt_candidate in [f"/app/.apt/usr/bin/{name}", f"/app/.apt/usr/local/bin/{name}"]:
        if os.path.isfile(apt_candidate) and _can_run(apt_candidate):
            return apt_candidate

    # 7. Static download fallback
    static_bin = _ensure_static_binary(name)
    if static_bin and _can_run(static_bin):
        return static_bin

    # 8. Last resort candidate
    for fallback in [vendor_candidate, f"/app/.apt/usr/bin/{name}", f"/usr/bin/{name}"]:
        if os.path.isfile(fallback):
            return fallback

    return name

FFMPEG_PATH  = _find_binary("ffmpeg",  "FFMPEG_PATH")
FFPROBE_PATH = _find_binary("ffprobe", "FFPROBE_PATH")
PW_TOKEN = os.environ.get("PW_TOKEN", "")

# ==============================================================================
# 🌐 WEB SERVER (Optional)
# ==============================================================================
WEB_SERVER = os.environ.get("WEB_SERVER", "False").lower() == "true"
WEBHOOK = True
PORT = int(os.environ.get("PORT", "8000"))

# ==============================================================================
# 💬 MESSAGE TEMPLATES
# ==============================================================================
AUTH_MESSAGES = {
    "subscription_active": """<b>🎉 Subscription Activated!</b>

<blockquote>Your subscription has been activated and will expire on {expiry_date}.
You can now use the bot!</blockquote>\n\n Type /start to start uploading """,

    "subscription_expired": """<b>⚠️ Your Subscription Has Ended</b>

<blockquote>Your access to the bot has been revoked as your subscription period has expired.
Please contact the admin to renew your subscription.</blockquote>""",

    "user_added": """<b>✅ User Added Successfully!</b>

<blockquote>👤 Name: {name}
🆔 User ID: {user_id}
📅 Expiry: {expiry_date}</blockquote>""",

    "user_removed": """<b>✅ User Removed Successfully!</b>

<blockquote>User ID {user_id} has been removed from authorized users.</blockquote>""",

    "access_denied": """<b>⚠️ Access Denied!</b>

<blockquote>You are not authorized to use this bot.
Please contact the admin to get access.</blockquote>""",

    "not_admin": "⚠️ You are not authorized to use this command!",
    
    "invalid_format": """❌ <b>Invalid Format!</b>

<blockquote>Use format: {format}</blockquote>"""
}
