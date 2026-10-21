"""
Client Helper for Course Wallah Bypass Service
Enables seamless integration in Downloader Bot and Platform.
"""

from typing import Dict, Any, Optional
from .engine import default_engine


def bypass_url(url: str, max_hops: int = 4) -> Dict[str, Any]:
    """
    Synchronously resolves and bypasses any shortlink or interstitial URL.
    Returns:
        dict with keys: 'success', 'original_url', 'bypassed_url', 'hops', 'handler', 'time_ms'
    """
    return default_engine.bypass(url, max_hops=max_hops)


async def async_bypass_url(url: str, max_hops: int = 4) -> Dict[str, Any]:
    """
    Asynchronously resolves and bypasses any shortlink or interstitial URL.
    """
    return await default_engine.abypass(url, max_hops=max_hops)
