"""
Indian Shortlink Networks Bypass Handler
Covers:
- GPLinks (gplinks.co, gplinks.in, api.gplinks.com)
- Droplink (droplink.co)
- ShrinkMe (shrinkme.io, shrinkme.in, shrinkme.cc, shrinkme.vip, shrinkme.ink, shrinkme.click)
- Rocklinks & VPLink (rocklinks.in, vplink.in, jrlinks.in, techmint.in)
- SoftURL (softurl.in)
- Linkshortify & Lksfy (lksfy.in, lksfy.com, linkshortify.in, linkshortify.com)
- AdLinkFly & WordPress Go-Link networks (4hi.in, clk.sh, dekhe.click, shrinkearn.com, etc.)
"""

import re
import json
import urllib.parse
from typing import Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
import cloudscraper

from .generic import extract_param_redirect, extract_html_base64_links, extract_js_redirect, extract_meta_refresh

# Common User Agent
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Host match patterns
INDIAN_SHORTENER_DOMAINS = [
    'gplinks', 'droplink', 'shrinkme', 'shrinkearn', 'shrinkforearn',
    'rocklinks', 'vplink', 'jrlinks', 'softurl', 'lksfy', 'linkshortify',
    'techmint', 'indianshortner', '4hi.in', 'dekhe.click', 'clk.wiki',
    'clk.kim', 'clk.sh', 'tnshort', 'srnky', 'tpi.li', 'lkfms', 'zshort'
]


def is_indian_shortener(url: str) -> bool:
    """Checks if the given URL belongs to an Indian shortlink network."""
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return any(d in host for d in INDIAN_SHORTENER_DOMAINS)
    except Exception:
        return False


def get_scraper() -> cloudscraper.CloudScraper:
    """Creates a configured cloudscraper session."""
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    scraper.headers.update({
        'User-Agent': DEFAULT_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    })
    return scraper


def bypass_gplinks(url: str) -> Optional[str]:
    """
    Bypasses gplinks.co / gplinks.in / api.gplinks.com.
    Uses cookie 'adexp=1' and follows through form tokens.
    """
    scraper = get_scraper()
    scraper.cookies.set('adexp', '1')
    
    try:
        res = scraper.get(url, timeout=12, allow_redirects=True)
        final_url = res.url
        if final_url != url and not any(k in final_url for k in ('gplinks', 'login')):
            return final_url
        
        # Check base64 in HTML
        b64_url = extract_html_base64_links(res.text, origin_domain="gplinks")
        if b64_url:
            return b64_url
            
        # Parse forms in page
        soup = BeautifulSoup(res.text, 'html.parser')
        form = soup.find('form', id='go-link') or soup.find('form')
        if form:
            action = form.get('action') or '/links/go'
            if not action.startswith('http'):
                action = urllib.parse.urljoin(url, action)
            
            form_data = {}
            for inp in form.find_all('input'):
                name = inp.get('name')
                val = inp.get('value', '')
                if name:
                    form_data[name] = val
                    
            post_headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': url,
                'Origin': f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
            }
            post_res = scraper.post(action, data=form_data, headers=post_headers, timeout=10)
            try:
                j = post_res.json()
                if j and isinstance(j, dict) and j.get('url'):
                    return j.get('url')
            except Exception:
                pass
                
        # Look for get-link anchors
        get_link_el = soup.find('a', class_=re.compile(r'get-link|btn-primary', re.I))
        if get_link_el and get_link_el.get('href') and get_link_el.get('href').startswith('http'):
            return get_link_el.get('href')
    except Exception as e:
        pass
    return None


def bypass_generic_golink(url: str) -> Optional[str]:
    """
    Generic solver for AdLinkFly and WordPress shortener networks
    (Droplink, ShrinkMe, Lksfy, SoftURL, Rocklinks, 4hi, Dekhe.click, etc.).
    Simulates token extraction, AJAX /links/go submission, and base64 unpacking.
    """
    scraper = get_scraper()
    try:
        res = scraper.get(url, timeout=12, allow_redirects=True)
        current_url = res.url
        origin_host = urllib.parse.urlparse(current_url).netloc.lower()

        # Step 1: Check query parameter redirect
        param_url = extract_param_redirect(current_url)
        if param_url:
            return param_url

        # Step 2: Check base64 in HTML
        b64_url = extract_html_base64_links(res.text, origin_domain=origin_host)
        if b64_url:
            return b64_url

        # Step 3: Check meta refresh or inline JS redirect
        meta_url = extract_meta_refresh(res.text, base_url=current_url)
        if meta_url and origin_host not in meta_url:
            return meta_url
            
        js_url = extract_js_redirect(res.text)
        if js_url and origin_host not in js_url:
            return js_url

        # Step 4: Parse forms (AdLinkFly standard 'form#go-link')
        soup = BeautifulSoup(res.text, 'html.parser')
        form = soup.find('form', id='go-link') or soup.find('form', id='link-view') or soup.find('form')
        
        if form:
            action = form.get('action') or '/links/go'
            if not action.startswith('http'):
                action = urllib.parse.urljoin(current_url, action)

            data = {}
            for inp in form.find_all('input'):
                name = inp.get('name')
                val = inp.get('value', '')
                if name:
                    data[name] = val

            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': current_url,
                'Origin': f"{urllib.parse.urlparse(current_url).scheme}://{urllib.parse.urlparse(current_url).netloc}"
            }
            
            post_res = scraper.post(action, data=data, headers=headers, timeout=10)
            try:
                rj = post_res.json()
                if isinstance(rj, dict) and rj.get('url'):
                    return rj.get('url')
            except Exception:
                # Might return a redirect header or HTML
                if post_res.url and post_res.url != current_url and origin_host not in post_res.url:
                    return post_res.url

        # Step 5: Check clickable buttons with direct links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            cls_text = ' '.join(a_tag.get('class', []))
            txt = a_tag.get_text().strip().lower()
            if any(w in txt for w in ('get link', 'continue', 'proceed', 'download')):
                if href.startswith('http') and origin_host not in href:
                    return href
                    
            if 'get-link' in cls_text and href.startswith('http') and origin_host not in href:
                return href

    except Exception:
        pass
    return None


def bypass_indian(url: str) -> Optional[str]:
    """Unified router for Indian shortlinks."""
    host = urllib.parse.urlparse(url).netloc.lower()
    
    if 'gplinks' in host:
        res = bypass_gplinks(url)
        if res:
            return res
            
    # Fallback to generic form solver
    return bypass_generic_golink(url)
