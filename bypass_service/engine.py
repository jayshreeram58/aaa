"""
Core Bypass Engine
Coordinates specialized handlers, cache, recursive multi-hop unshortening,
and performance benchmarking.
"""

import time
import asyncio
import urllib.parse
from typing import Optional, Dict, Any, List
import threading

from .handlers import (
    extract_param_redirect,
    extract_html_base64_links,
    extract_meta_refresh,
    extract_js_redirect,
    bypass_indian,
    is_indian_shortener,
    bypass_filehost,
    is_filehost,
    follow_http_redirects,
    unshorten_via_free_api,
    bypass_with_headless_browser
)


# 6-Hour Cache TTL
CACHE_TTL = 6 * 3600


class BypassEngine:
    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_cache(self, url: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._cache.get(url)
            if entry and (time.time() - entry['timestamp']) < self.cache_ttl:
                return entry['data']
            return None

    def _set_cache(self, url: str, data: Dict[str, Any]):
        with self._lock:
            self._cache[url] = {
                'data': data,
                'timestamp': time.time()
            }

    def bypass(self, url: str, max_hops: int = 4) -> Dict[str, Any]:
        """
        Synchronously resolves/bypasses a shortlink or interstitial redirect.
        Supports multi-hop chains (e.g., vplink -> techmint -> gdrive).
        """
        start_time = time.time()
        url = (url or '').strip()

        if not url:
            return {
                "success": False,
                "error": "URL cannot be empty",
                "original_url": url,
                "bypassed_url": None,
                "time_ms": 0
            }

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Check Cache
        cached_result = self._get_cache(url)
        if cached_result:
            res = dict(cached_result)
            res['cached'] = True
            res['time_ms'] = round((time.time() - start_time) * 1000, 2)
            return res

        current_url = url
        hops_taken = 0
        used_handler = "direct"
        history: List[str] = [current_url]

        for hop in range(max_hops):
            bypassed = None
            handler_name = None

            # 1. Parameter extraction check (instant)
            param_url = extract_param_redirect(current_url)
            if param_url and param_url != current_url:
                bypassed = param_url
                handler_name = "param_unpacker"

            # 2. Indian Shortener Handler
            if not bypassed and is_indian_shortener(current_url):
                indian_res = bypass_indian(current_url)
                if indian_res and indian_res != current_url:
                    bypassed = indian_res
                    handler_name = "indian_engine"

            # 3. Filehost Handler
            if not bypassed and is_filehost(current_url):
                file_res = bypass_filehost(current_url)
                if file_res and file_res != current_url:
                    bypassed = file_res
                    handler_name = "filehost_extractor"

            # 4. HTTP 301/302 Redirect Tracer
            if not bypassed:
                redirect_res = follow_http_redirects(current_url)
                if redirect_res and redirect_res != current_url:
                    bypassed = redirect_res
                    handler_name = "http_redirect"

            # 5. Public API Fallback
            if not bypassed:
                free_res = unshorten_via_free_api(current_url)
                if free_res and free_res != current_url:
                    bypassed = free_res
                    handler_name = "unshorten_api"

            # 6. Headless Browser Solver with Userscript Injection (Ultimate 100% Final Solver)
            if not bypassed:
                browser_res = bypass_with_headless_browser(current_url, max_wait_sec=14)
                if browser_res and browser_res != current_url:
                    bypassed = browser_res
                    handler_name = "headless_browser_userscript"

            # If a new URL was unlocked
            if bypassed and bypassed != current_url and bypassed not in history:

                current_url = bypassed
                hops_taken += 1
                used_handler = handler_name or "chain"
                history.append(current_url)
            else:
                break

        elapsed = round((time.time() - start_time) * 1000, 2)
        is_success = (current_url != url)

        result = {
            "success": is_success,
            "original_url": url,
            "bypassed_url": current_url if is_success else url,
            "hops": hops_taken,
            "history": history,
            "handler": used_handler,
            "cached": False,
            "time_ms": elapsed
        }

        if is_success:
            self._set_cache(url, result)

        return result

    async def abypass(self, url: str, max_hops: int = 4) -> Dict[str, Any]:
        """Asynchronous wrapper for bypass engine."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.bypass, url, max_hops)


# Default global instance
default_engine = BypassEngine()
