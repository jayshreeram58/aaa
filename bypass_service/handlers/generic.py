"""
Generic Bypass & Unshortening Handlers
Handles standard HTTP redirects, base64 unpacked links, query parameter redirects,
meta-refresh headers, and inline JavaScript redirection extraction.
"""

import re
import base64
import urllib.parse
from typing import Optional, Dict, Any

# Common query params shorteners use to forward users
REDIRECT_PARAMS = [
    'r', 'url', 'dest', 'destination', 'target', 'link', 'to', 'out',
    'goto', 'redirect', 'redirect_to', 'next', 'forward', 'ref', 'dl', 'down'
]

# Base64 URL signature regex (aHR0c... is base64 for 'http')
B64_HTTP_REGEX = re.compile(r'aHR0c[a-zA-Z0-9+/=]{10,}')
META_REFRESH_REGEX = re.compile(r'<meta[^>]*?http-equiv=["\']refresh["\'][^>]*?content=["\']\d+;\s*url=([^"\']+)["\']', re.IGNORECASE)
JS_REDIRECT_REGEX = re.compile(r'(?:window\.)?location(?:\.href|\.assign|\.replace)?\s*=\s*["\'](https?://[^"\']+)["\']', re.IGNORECASE)


def decode_base64_safe(data: str) -> Optional[str]:
    """Attempts safe base64 decoding with padding fix."""
    if not data or not isinstance(data, str):
        return None
    data = data.strip()
    # Add missing padding if needed
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    try:
        decoded = base64.b64decode(data, validate=False).decode('utf-8', errors='ignore')
        if decoded.startswith(('http://', 'https://')):
            return decoded.strip()
    except Exception:
        pass
    return None


def extract_param_redirect(url: str) -> Optional[str]:
    """
    Extracts embedded target URLs from query parameters (either raw or base64 encoded).
    Example: ?r=aHR0cHM6Ly9leGFtcGxlLmNvbQ== or ?url=https%3A%2F%2Fexample.com
    """
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        for key in REDIRECT_PARAMS:
            for val in params.get(key, []):
                val = val.strip()
                # Check direct url
                if val.startswith(('http://', 'https://')):
                    return val
                # Check base64 encoded url
                b64_res = decode_base64_safe(val)
                if b64_res:
                    return b64_res
    except Exception:
        pass
    return None


def extract_html_base64_links(html: str, origin_domain: str = "") -> Optional[str]:
    """
    Scans raw HTML for hidden base64 encoded URLs starting with 'http' (aHR0c...).
    Used by sites like tpi.li, srnky, dekhe.click, etc.
    """
    if not html:
        return None
    matches = B64_HTTP_REGEX.findall(html)
    for m in matches:
        decoded = decode_base64_safe(m)
        if decoded:
            try:
                dec_host = urllib.parse.urlparse(decoded).netloc.lower()
                # Ensure the link points to a destination, not the shortener host itself
                if origin_domain and origin_domain.lower() in dec_host:
                    continue
                return decoded
            except Exception:
                return decoded
    return None


def extract_meta_refresh(html: str, base_url: str = "") -> Optional[str]:
    """Extracts <meta http-equiv="refresh" content="0;url=..."> redirects."""
    if not html:
        return None
    match = META_REFRESH_REGEX.search(html)
    if match:
        target = match.group(1).strip()
        if base_url and not target.startswith(('http://', 'https://')):
            target = urllib.parse.urljoin(base_url, target)
        return target
    return None


def extract_js_redirect(html: str) -> Optional[str]:
    """Extracts window.location.href = '...' redirections."""
    if not html:
        return None
    match = JS_REDIRECT_REGEX.search(html)
    if match:
        return match.group(1).strip()
    return None
