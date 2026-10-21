"""
Bypass Service Handlers Package
"""
from .generic import (
    decode_base64_safe,
    extract_param_redirect,
    extract_html_base64_links,
    extract_meta_refresh,
    extract_js_redirect,
)
from .indian import bypass_indian, is_indian_shortener
from .filehost import bypass_filehost, is_filehost
from .public_api import follow_http_redirects, unshorten_via_free_api

__all__ = [
    'decode_base64_safe',
    'extract_param_redirect',
    'extract_html_base64_links',
    'extract_meta_refresh',
    'extract_js_redirect',
    'bypass_indian',
    'is_indian_shortener',
    'bypass_filehost',
    'is_filehost',
    'follow_http_redirects',
    'unshorten_via_free_api',
]
