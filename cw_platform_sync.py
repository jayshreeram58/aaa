import os
import re
import json
import time
import base64
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

import requests

logger = logging.getLogger("CourseWallahSync")

# Base storage paths
BOT_ROOT = Path(__file__).resolve().parent
LOCAL_DATA_DIR = BOT_ROOT / "data"

# Optional sibling platform path if running locally
SIBLING_PLATFORM_DATA = BOT_ROOT.parent / "course-wallah-platform" / "data"

# GitHub synchronization configuration
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", "")).strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "ramjipatel-tech/course-wallah-platform").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()

DEFAULT_APPS = [
    {
        "id": "physics_wallah",
        "name": "Physics Wallah",
        "description": "JEE, NEET, Boards & Foundation Batches",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/pw_brand_icon.jpg"
    },
    {
        "id": "selection_way",
        "name": "Selection Way",
        "description": "SSC, Railway, Banking, Police Exam Preparation",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/selection_way_brand_icon.svg"
    },
    {
        "id": "unacademy",
        "name": "Unacademy",
        "description": "IIT JEE, NEET UG, GATE & UPSC Classes",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/unacademy_brand_icon.jpg"
    },
    {
        "id": "apna_college",
        "name": "Apna College",
        "description": "Delta Web Dev, Alpha & Sigma DSA Courses",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/apna_college_brand_icon.jpg"
    },
    {
        "id": "technical_classes",
        "name": "Technical Classes",
        "description": "Polytechnic & Engineering Semester Courses",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/technical_classes_brand_icon.svg"
    },
    {
        "id": "storytv",
        "name": "StoryTV",
        "description": "Vertical Reels Micro-Series & Short Dramas",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/storytv_brand_icon.svg"
    },
    {
        "id": "sonyliv",
        "name": "SonyLIV",
        "description": "Entertainment Shows, Sitcoms & Originals",
        "icon": "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/sonyliv_brand_icon.svg"
    }
]

_SYNC_LOCK = threading.RLock()


def slugify(text: str) -> str:
    """Converts a title or name into a safe, normalized identifier."""
    if not text:
        return "general"
    clean = re.sub(r"[^\w\s-]", "", str(text)).strip().lower()
    clean = re.sub(r"[-\s]+", "_", clean)
    return clean or "general"


class CourseWallahPlatformSync:
    """
    Manages Course Wallah Platform App creation, Batch JSON indexing,
    Telegram Player URL formatting, and GitHub Git-as-a-Database commits.
    """

    @classmethod
    def get_apps_file(cls) -> Path:
        f = LOCAL_DATA_DIR / "apps.json"
        if not f.exists():
            LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(DEFAULT_APPS, fp, indent=2, ensure_ascii=False)
        return f

    @classmethod
    def get_all_apps(cls) -> List[Dict[str, Any]]:
        with _SYNC_LOCK:
            f = cls.get_apps_file()
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception as e:
                logger.warning(f"Error reading apps.json: {e}")
                return DEFAULT_APPS

    @classmethod
    def get_app_by_slug(cls, slug_or_name: str) -> Optional[Dict[str, Any]]:
        target = slugify(slug_or_name)
        for app in cls.get_all_apps():
            if slugify(app.get("id", "")) == target or slugify(app.get("name", "")) == target:
                return app
        return None

    @classmethod
    def create_new_app(cls, name: str, description: str = "", icon_url: str = "") -> Dict[str, Any]:
        """Creates a new educational app on Course Wallah platform."""
        with _SYNC_LOCK:
            app_id = slugify(name)
            apps = cls.get_all_apps()

            for existing in apps:
                if existing.get("id") == app_id:
                    existing["name"] = name
                    if description:
                        existing["description"] = description
                    if icon_url:
                        existing["icon"] = icon_url
                    cls._save_apps(apps)
                    return existing

            new_app = {
                "id": app_id,
                "name": name.strip(),
                "description": description.strip() or f"{name} Courses & Batches",
                "icon": icon_url.strip() or "https://raw.githubusercontent.com/ramjipatel-tech/course-wallah-platform/main/web/public/icons/pw_brand_icon.jpg"
            }
            apps.append(new_app)
            cls._save_apps(apps)

            # Create data directory structure for this new app
            app_batch_dir = LOCAL_DATA_DIR / app_id / "batches"
            app_batch_dir.mkdir(parents=True, exist_ok=True)

            idx_file = LOCAL_DATA_DIR / app_id / "batches_index.json"
            if not idx_file.exists():
                with open(idx_file, "w", encoding="utf-8") as fp:
                    json.dump([], fp, indent=2)

            logger.info(f"🎉 Created new Course Wallah App: '{name}' (ID: {app_id})")
            return new_app

    @classmethod
    def _save_apps(cls, apps: List[Dict[str, Any]]):
        f = cls.get_apps_file()
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(apps, fp, indent=2, ensure_ascii=False)

        # Sync to sibling platform directory if present
        if SIBLING_PLATFORM_DATA.exists():
            try:
                sib_apps = SIBLING_PLATFORM_DATA / "apps.json"
                with open(sib_apps, "w", encoding="utf-8") as fp:
                    json.dump(apps, fp, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.debug(f"Could not sync apps to sibling platform: {e}")

        # Sync to remote GitHub repo if token configured
        if GITHUB_TOKEN:
            try:
                cls._github_put_file(
                    file_path="data/apps.json",
                    content=apps,
                    commit_msg="feat(apps): update Course Wallah platform apps catalog"
                )
            except Exception as ge:
                logger.debug(f"Could not push apps.json to GitHub: {ge}")

    @classmethod
    def get_batch_file(cls, app_slug: str, batch_slug: str) -> Path:
        safe_app = slugify(app_slug)
        safe_b = slugify(batch_slug)
        d = LOCAL_DATA_DIR / safe_app / "batches"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{safe_b}.json"

    @classmethod
    def get_batch(cls, app_slug: str, batch_slug: str) -> Optional[Dict[str, Any]]:
        bf = cls.get_batch_file(app_slug, batch_slug)
        if bf.exists():
            try:
                with open(bf, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                pass
        return None

    @classmethod
    def check_batch_exists(cls, app_slug: str, batch_name: str) -> bool:
        safe_b = slugify(batch_name)
        bf = cls.get_batch_file(app_slug, safe_b)
        return bf.exists()

    @classmethod
    def record_lecture_upload(
        cls,
        app_slug: str,
        app_name: str,
        batch_name: str,
        channel_id: Any,
        index: int,
        title: str,
        subject: str = "General",
        folder: str = "Lectures",
        video_msg_id: Optional[int] = None,
        duration: int = 0,
        thumbnail: str = "",
        pdf_msg_id: Optional[int] = None,
        pdf_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records an uploaded lecture video and/or PDF note into Course Wallah batch JSON.
        Forms valid streaming endpoints:
        /api/v1/stream/tg/{message_id}?chat_id={channel_id}
        """
        with _SYNC_LOCK:
            safe_app = slugify(app_slug)
            safe_b = slugify(batch_name)
            bf = cls.get_batch_file(safe_app, safe_b)

            batch_data = cls.get_batch(safe_app, safe_b)
            if not batch_data:
                batch_data = {
                    "platform": app_name or "Course Wallah",
                    "appId": safe_app,
                    "batchId": safe_b,
                    "batchSlug": safe_b,
                    "batchName": batch_name,
                    "category": "General",
                    "thumbnail": thumbnail or "",
                    "channelId": channel_id,
                    "totalSections": 0,
                    "totalLectures": 0,
                    "totalNotes": 0,
                    "sections": []
                }

            # Find or create section
            sec_name = f"{subject} - {folder}" if folder and folder != subject else subject
            sec_id = slugify(sec_name)

            target_section = None
            for sec in batch_data["sections"]:
                if sec.get("sectionId") == sec_id or sec.get("sectionName") == sec_name:
                    target_section = sec
                    break

            if not target_section:
                target_section = {
                    "sectionId": sec_id,
                    "sectionName": sec_name,
                    "totalLectures": 0,
                    "lectures": [],
                    "notes": []
                }
                batch_data["sections"].append(target_section)

            # Lecture streaming URL
            video_stream_url = f"/api/v1/stream/tg/{video_msg_id}?chat_id={channel_id}" if video_msg_id else None
            pdf_stream_url = f"/api/v1/stream/tg/{pdf_msg_id}?chat_id={channel_id}" if pdf_msg_id else pdf_url

            # Find existing lecture by index or append
            existing_lec = None
            for lec in target_section["lectures"]:
                if lec.get("index") == index:
                    existing_lec = lec
                    break

            lec_id = f"lec_{safe_b}_{index:03d}"

            if existing_lec:
                existing_lec["title"] = title
                if video_stream_url:
                    existing_lec["videoUrl"] = video_stream_url
                    existing_lec["messageId"] = video_msg_id
                    existing_lec["channelId"] = channel_id
                if duration:
                    existing_lec["duration"] = duration
                if thumbnail and not existing_lec.get("thumbnail"):
                    existing_lec["thumbnail"] = thumbnail
            else:
                new_lec = {
                    "lectureId": lec_id,
                    "index": index,
                    "title": title,
                    "duration": duration,
                    "messageId": video_msg_id,
                    "channelId": channel_id,
                    "videoUrl": video_stream_url,
                    "thumbnail": thumbnail or batch_data.get("thumbnail", "")
                }
                target_section["lectures"].append(new_lec)

            # If PDF notes exist for this lecture
            if pdf_stream_url:
                note_id = f"note_{safe_b}_{index:03d}"
                existing_note = None
                for n in target_section.get("notes", []):
                    if n.get("index") == index or n.get("noteId") == note_id:
                        existing_note = n
                        break

                if existing_note:
                    existing_note["pdfUrl"] = pdf_stream_url
                    if pdf_msg_id:
                        existing_note["messageId"] = pdf_msg_id
                else:
                    target_section["notes"].append({
                        "noteId": note_id,
                        "index": index,
                        "title": f"{title} (Notes)",
                        "messageId": pdf_msg_id,
                        "pdfUrl": pdf_stream_url
                    })

            # Recalculate totals
            tot_l = sum(len(s.get("lectures", [])) for s in batch_data["sections"])
            tot_n = sum(len(s.get("notes", [])) for s in batch_data["sections"])
            batch_data["totalSections"] = len(batch_data["sections"])
            batch_data["totalLectures"] = tot_l
            batch_data["totalNotes"] = tot_n
            for s in batch_data["sections"]:
                s["totalLectures"] = len(s.get("lectures", []))

            # Save to disk
            with open(bf, "w", encoding="utf-8") as fp:
                json.dump(batch_data, fp, indent=2, ensure_ascii=False)

            # Update batches_index.json
            idx_file = LOCAL_DATA_DIR / safe_app / "batches_index.json"
            idx_list = []
            if idx_file.exists():
                try:
                    with open(idx_file, "r", encoding="utf-8") as fp:
                        idx_list = json.load(fp)
                except Exception:
                    idx_list = []

            idx_list = [b for b in idx_list if b.get("batchId") != safe_b and b.get("batchSlug") != safe_b]
            idx_list.append({
                "batchId": safe_b,
                "batchSlug": safe_b,
                "batchName": batch_name,
                "category": batch_data.get("category", "General"),
                "thumbnail": batch_data.get("thumbnail", ""),
                "totalLectures": tot_l,
                "totalNotes": tot_n
            })

            with open(idx_file, "w", encoding="utf-8") as fp:
                json.dump(idx_list, fp, indent=2, ensure_ascii=False)

            # Sync to sibling platform data folder if available
            if SIBLING_PLATFORM_DATA.exists():
                try:
                    sib_b_dir = SIBLING_PLATFORM_DATA / safe_app / "batches"
                    sib_b_dir.mkdir(parents=True, exist_ok=True)
                    with open(sib_b_dir / f"{safe_b}.json", "w", encoding="utf-8") as fp:
                        json.dump(batch_data, fp, indent=2, ensure_ascii=False)
                    with open(SIBLING_PLATFORM_DATA / safe_app / "batches_index.json", "w", encoding="utf-8") as fp:
                        json.dump(idx_list, fp, indent=2, ensure_ascii=False)
                except Exception as se:
                    logger.debug(f"Could not write to sibling platform: {se}")

            logger.info(f"✅ Recorded lecture #{index} '{title}' in batch JSON [{safe_app}/{safe_b}]")
            return batch_data

    @classmethod
    def push_to_github(cls, app_slug: str, batch_slug: str) -> bool:
        """Pushes the updated batch JSON and index to GitHub via GitHub API."""
        if not GITHUB_TOKEN:
            logger.debug("GITHUB_TOKEN not provided; skipping remote GitHub API commit.")
            return False

        safe_app = slugify(app_slug)
        safe_b = slugify(batch_slug)
        bf = cls.get_batch_file(safe_app, safe_b)
        idx_file = LOCAL_DATA_DIR / safe_app / "batches_index.json"

        if not bf.exists():
            logger.warning(f"Batch file '{bf}' does not exist; cannot push to GitHub.")
            return False

        try:
            with open(bf, "r", encoding="utf-8") as fp:
                b_content = json.load(fp)

            ok1 = cls._github_put_file(
                file_path=f"data/{safe_app}/batches/{safe_b}.json",
                content=b_content,
                commit_msg=f"feat(stream): sync batch {safe_b} in {safe_app} with live Telegram stream URLs"
            )

            ok2 = True
            if idx_file.exists():
                with open(idx_file, "r", encoding="utf-8") as fp:
                    idx_content = json.load(fp)
                ok2 = cls._github_put_file(
                    file_path=f"data/{safe_app}/batches_index.json",
                    content=idx_content,
                    commit_msg=f"feat(catalog): update batches index for {safe_app}"
                )

            if ok1 and ok2:
                logger.info(f"🚀 Pushed batch '{safe_b}' JSON to GitHub: {GITHUB_REPO} ({GITHUB_BRANCH})")
                return True
            else:
                logger.warning(f"⚠️ GitHub sync failed for '{safe_b}'. Data remains saved locally.")
                return False
        except Exception as e:
            logger.warning(f"Failed to push batch to GitHub: {e}")
            return False

    @classmethod
    def _github_put_file(cls, file_path: str, content: Any, commit_msg: str) -> bool:
        if not GITHUB_TOKEN:
            return False

        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CourseWallah-Sync/1.0"
        }

        # Check existing SHA
        sha = None
        try:
            r = requests.get(f"{url}?ref={GITHUB_BRANCH}", headers=headers, timeout=15)
            if r.status_code == 200:
                sha = r.json().get("sha")
            elif r.status_code == 401:
                logger.error("❌ GitHub Token Authentication Failed (401 Bad credentials). Please verify your GITHUB_TOKEN in Colab / environment.")
                return False
            elif r.status_code == 404:
                sha = None  # New file
        except Exception as ge:
            logger.warning(f"Error fetching existing GitHub SHA for {file_path}: {ge}")

        b64_content = base64.b64encode(json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")).decode("utf-8")
        payload = {
            "message": commit_msg,
            "content": b64_content,
            "branch": GITHUB_BRANCH
        }
        if sha:
            payload["sha"] = sha

        try:
            resp = requests.put(url, headers=headers, json=payload, timeout=25)
            if resp.status_code in (200, 201):
                logger.debug(f"GitHub PUT {file_path} succeeded ({resp.status_code})")
                return True
            elif resp.status_code == 401:
                logger.error(f"❌ GitHub Authentication Failed (401 Bad credentials) on PUT {file_path}. GITHUB_TOKEN is expired or invalid.")
                return False
            else:
                logger.warning(f"GitHub PUT {file_path} returned {resp.status_code}: {resp.text}")
                return False
        except Exception as pe:
            logger.warning(f"GitHub PUT request exception for {file_path}: {pe}")
            return False
