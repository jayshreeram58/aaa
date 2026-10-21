"""
Public & Cloud Unshortener / Bypasser Handlers
Provides multi-hop HTTP redirect following and public unshortener API fallbacks.
"""

import requests
import urllib.parse
from typing import Optional


def follow_http_redirects(url: str, max_hops: int = 10) -> Optional[str]:
    """
    Traces HTTP redirect chain (301, 302, 303, 307, 308) to find the final landing URL.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    current_url = url
    session = requests.Session()
    
    try:
        # Use HEAD first for speed
        res = session.head(current_url, headers=headers, allow_redirects=True, timeout=8)
        if res.url and res.url != current_url:
            return res.url
    except Exception:
        pass
        
    try:
        # Fall back to GET with stream=True so body isn't downloaded
        res = session.get(current_url, headers=headers, allow_redirects=True, stream=True, timeout=10)
        if res.url and res.url != current_url:
            return res.url
    except Exception:
        pass
        
    return None


def unshorten_via_free_api(url: str) -> Optional[str]:
    """
    Queries unshorten.me free API for known global shortener domains.
    """
    try:
        api_endpoint = f"https://unshorten.me/json/{urllib.parse.quote(url, safe='')}"
        res = requests.get(api_endpoint, timeout=8)
        if res.status_code == 200:
            data = res.json()
            if data.get('success') and data.get('resolved_url'):
                resolved = data['resolved_url']
                if resolved != url:
                    return resolved
    except Exception:
        pass
    return None
