"""
File Hoster Fast Direct-Link Extractors
Covers:
- modsfire.com
- cloudfam.io
- uploady.io
- mega4upload.net
- dailyuploads.net
- jioupload (jioupload.link, jioupload.icu, totoly.monster)
- frdl (frdl.io, freedl.ink, frdl.is)
"""

import re
import urllib.parse
from typing import Optional
from bs4 import BeautifulSoup
import cloudscraper

FILEHOST_DOMAINS = [
    'modsfire.com', 'cloudfam.io', 'uploady.io', 'mega4upload.net',
    'dailyuploads.net', 'jioupload.link', 'jioupload.com', 'jioupload.icu',
    'totoly.monster', 'frdl.io', 'freedl.ink', 'frdl.is'
]


def is_filehost(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return any(d in host for d in FILEHOST_DOMAINS)
    except Exception:
        return False


def get_scraper() -> cloudscraper.CloudScraper:
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    scraper.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    })
    return scraper


def bypass_modsfire(url: str) -> Optional[str]:
    scraper = get_scraper()
    try:
        res = scraper.get(url, timeout=12)
        soup = BeautifulSoup(res.text, 'html.parser')
        btn = soup.find('a', class_=re.compile(r'download-button', re.I))
        if btn and btn.get('href'):
            href = btn.get('href')
            if href.startswith(('http://', 'https://')):
                return href
            return urllib.parse.urljoin(url, href)
    except Exception:
        pass
    return None


def bypass_cloudfam(url: str) -> Optional[str]:
    scraper = get_scraper()
    try:
        res = scraper.get(url, timeout=12)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Check for redirection0.php or direct apk / download handler
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(k in href for k in ('redirection0.php', 'redirection', 'download_handler.php', '.apk')):
                if href.startswith(('http://', 'https://')):
                    return href
                return urllib.parse.urljoin(url, href)
    except Exception:
        pass
    return None


def bypass_uploady(url: str) -> Optional[str]:
    scraper = get_scraper()
    try:
        res = scraper.get(url, timeout=12)
        soup = BeautifulSoup(res.text, 'html.parser')
        f1 = soup.find('form', id='F1') or soup.find('form')
        if f1:
            action = f1.get('action') or url
            if not action.startswith('http'):
                action = urllib.parse.urljoin(url, action)
            data = {}
            for inp in f1.find_all('input'):
                n = inp.get('name')
                v = inp.get('value', '')
                if n:
                    data[n] = v
            post_res = scraper.post(action, data=data, timeout=12, allow_redirects=True)
            if post_res.url and post_res.url != url:
                return post_res.url
    except Exception:
        pass
    return None


def bypass_generic_filehost(url: str) -> Optional[str]:
    scraper = get_scraper()
    try:
        res = scraper.get(url, timeout=12)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Look for free download button / anchor
        for a in soup.find_all(['a', 'button']):
            txt = a.get_text().strip().lower()
            if any(w in txt for w in ('download', 'direct download', 'proceed to download')):
                href = a.get('href')
                if href and href.startswith('http') and url not in href:
                    return href

        # Look for form submission
        forms = soup.find_all('form')
        for form in forms:
            action = form.get('action') or url
            if not action.startswith('http'):
                action = urllib.parse.urljoin(url, action)
            data = {}
            for inp in form.find_all('input'):
                n = inp.get('name')
                v = inp.get('value', '')
                if n:
                    data[n] = v
            if 'op' in data or 'download' in str(form).lower():
                post_res = scraper.post(action, data=data, timeout=12, allow_redirects=True)
                if post_res.url and post_res.url != url:
                    return post_res.url
    except Exception:
        pass
    return None


def bypass_filehost(url: str) -> Optional[str]:
    host = urllib.parse.urlparse(url).netloc.lower()
    if 'modsfire' in host:
        res = bypass_modsfire(url)
        if res:
            return res
    elif 'cloudfam' in host:
        res = bypass_cloudfam(url)
        if res:
            return res
    elif 'uploady' in host:
        res = bypass_uploady(url)
        if res:
            return res
    return bypass_generic_filehost(url)
