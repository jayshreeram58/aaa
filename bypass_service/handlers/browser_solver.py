"""
Playwright Headless Browser Solver with Userscript Injection
Executes JavaScript countdown timers, clicks proceed buttons, and follows multi-step
blog networks to extract the 100% FINAL destination URL.
"""

import os
import sys
import time
import urllib.parse
from typing import Optional

# Path to the bundled Bypass_Shortlinks.user.js
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ROOT = os.path.dirname(CURRENT_DIR)
WORKSPACE_ROOT = os.path.dirname(SERVICE_ROOT)
USERSCRIPT_PATH = os.path.join(WORKSPACE_ROOT, "bypass-shortlinks", "Bypass_Shortlinks.user.js")

_cached_script_code = None


def get_userscript_code() -> str:
    """Reads and strips metadata header from the userscript."""
    global _cached_script_code
    if _cached_script_code is not None:
        return _cached_script_code
        
    candidates = [
        USERSCRIPT_PATH,
        r"B:\Projects\downloader bot\bypass-shortlinks\Bypass_Shortlinks.user.js",
        r"B:\Projects\experiment\course-wallah-downloader-bot\bypass-shortlinks\Bypass_Shortlinks.user.js",
    ]
    
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    code = f.read()
                header_end = code.find("// ==/UserScript==")
                if header_end != -1:
                    _cached_script_code = code[header_end + len("// ==/UserScript=="):]
                else:
                    _cached_script_code = code
                return _cached_script_code
            except Exception:
                pass
    return ""


def bypass_with_headless_browser(target_url: str, max_wait_sec: int = 15) -> Optional[str]:
    """
    Spawns a headless Chromium browser instance, injects the Bypass Shortlinks userscript,
    and waits for the browser to navigate through intermediate ad/countdown pages
    to reach the 100% FINAL destination link.
    """
    userscript = get_userscript_code()
    if not userscript:
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        parsed = urllib.parse.urlparse(target_url)
        initial_host = parsed.netloc.lower()

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            # Inject userscript at document-start before any site scripts execute
            context.add_init_script(userscript)
            
            page = context.new_page()
            try:
                page.goto(target_url, timeout=max_wait_sec * 1000, wait_until="domcontentloaded")
            except Exception:
                # Page might redirect or abort initial navigation, continue checking URL
                pass

            start_time = time.time()
            final_url = page.url

            # Poll for redirection to settle at the final destination
            while time.time() - start_time < max_wait_sec:
                time.sleep(0.6)
                current = page.url
                curr_host = urllib.parse.urlparse(current).netloc.lower()

                # If URL navigated away from initial shortlink host and is a valid web page
                if curr_host and curr_host != initial_host and not any(k in curr_host for k in ('about:blank', 'localhost')):
                    final_url = current
                    # If it arrived at Google Drive, Mega, Mediafire, Terabox, or direct media, break immediately
                    if any(fav in curr_host for fav in ('drive.google', 'mega.nz', 'mediafire', 'terabox', 'youtube', 'github', 't.me')):
                        break

            browser.close()

            if final_url and final_url != target_url:
                return final_url
    except Exception as e:
        print(f"[BROWSER SOLVER ERROR] {e}")

    return None
