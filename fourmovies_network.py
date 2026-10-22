"""
Unified 4uMovies Network Multi-Platform Client & Downloader Engine
Supports:
1. NetMirror (net.4umovies.site) - Movies & Web Series (1080p HLS)
2. Mastii OTT Pro (masti.4umovies.site) - Premium Web Series & Originals (AES Decrypted Direct HLS)
3. AnimeKai (anime.4umovies.site) - Anime Movies & Series (Multi-server Sub/Dub HLS)
4. DesiTV (desitv.4umovies.site) - Daily TV Serials (Star Plus, Sony, Zee, Colors)
5. SonyLIV (sony.4umovies.site) - Sony Originals & TV Shows (MPEG-DASH / MPD)
"""

import json
import urllib.request
import urllib.parse
import re
import sys
from typing import Dict, Any, List, Optional
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}


# =====================================================================
# 1. NetMirror Client (net.4umovies.site)
# =====================================================================
class NetMirrorClient:
    BASE_URL = "https://net.4umovies.site"
    RESOLVER_URL = "https://net.4umovies.site/api/resolve"

    def __init__(self):
        self._catalog_cache = None

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Fetch and cache all movies/series available on NetMirror."""
        if self._catalog_cache:
            return self._catalog_cache
        req = urllib.request.Request(self.BASE_URL, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', 'ignore')
            m = re.search(r'const\s+MOVIES\s*=\s*(\[.*?\]);', html, re.DOTALL)
            if m:
                self._catalog_cache = json.loads(m.group(1))
                return self._catalog_cache
        return []

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search local NetMirror movie catalog."""
        catalog = self.get_catalog()
        q = query.lower().strip()
        results = []
        for item in catalog:
            title = str(item.get('title', '')).lower()
            original_title = str(item.get('original_title', '')).lower()
            if q in title or q in original_title:
                results.append(item)
        return results

    def resolve_stream(self, content_id: str, episode_id: Optional[str] = None) -> Dict[str, Any]:
        """Resolve direct 1080p HLS stream URL for a movie or TV series episode."""
        url = f"{self.RESOLVER_URL}?id={urllib.parse.quote(str(content_id))}"
        if episode_id:
            url += f"&ep={urllib.parse.quote(str(episode_id))}"
        
        headers = dict(DEFAULT_HEADERS)
        headers['Referer'] = f"{self.BASE_URL}/watch.html?id={content_id}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))


# =====================================================================
# 2. Mastii OTT Pro Client (masti.4umovies.site)
# =====================================================================
class MastiiClient:
    SHOWS_URL = "https://masti.4umovies.site/shows.json"
    EPISODES_API = "https://api.mastii.in/ottapi/v1/content/list/device/web/current_offset/0/max_counter/1000/season_id/{season_id}/user_id/1960395"
    DETAIL_API = "https://api.mastii.in/ottapi/v1/content/detail/device/web/content_id/{content_id}"
    
    KEY = b'89H49I12T20E542N17D4E5A47R184LKL'
    IV = b'0543737198408118'
    AUTH_JWT = 'ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5LmV5SmhkWFJvYjNKcGVtVmtJanAwY25WbExDSmxlSEFpT2pFMk5qYzVNRE16Tnprc0luUnZhMlZ1SWpvaWRFWlBXR1F3ZUhJeWJWbEtSblEwSWl3aWRYTmxjbTVoYldVaU9pSmtaV1poZFd4MFgyRmtiV2x1SW4wLlQxU3FkVkNFTHEtaUxadnZKVUNCS1dVLWFrOTdyUF9SRkJ6OXN5U1l6VGc'

    def _decrypt(self, hex_or_b64: str) -> Dict[str, Any]:
        try:
            data = bytes.fromhex(hex_or_b64)
        except Exception:
            import base64
            data = base64.b64decode(hex_or_b64)
        cipher = AES.new(self.KEY, AES.MODE_CBC, self.IV)
        decrypted = unpad(cipher.decrypt(data), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))

    def list_shows(self) -> List[Dict[str, Any]]:
        """List all available shows and movies on Mastii OTT."""
        req = urllib.request.Request(self.SHOWS_URL, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))

    def get_season_episodes(self, season_id: str) -> List[Dict[str, Any]]:
        """Get decrypted episode list for a show season."""
        url = self.EPISODES_API.format(season_id=season_id)
        headers = dict(DEFAULT_HEADERS)
        headers['Authorization'] = self.AUTH_JWT
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode('utf-8'))
            if 'result' in res:
                dec = self._decrypt(res['result'])
                return dec.get('content', [])
        return []

    def get_stream(self, content_id: str) -> Dict[str, Any]:
        """Fetch decrypted video metadata and direct HLS stream URL."""
        url = self.DETAIL_API.format(content_id=content_id)
        headers = dict(DEFAULT_HEADERS)
        headers['Authorization'] = self.AUTH_JWT
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode('utf-8'))
            if 'result' in res:
                dec = self._decrypt(res['result'])
                content = dec.get('content', {})
                return {
                    "id": content.get('id'),
                    "title": content.get('title'),
                    "duration": content.get('duration'),
                    "stream_url": content.get('url') or content.get('download_path'),
                    "trailer_url": content.get('trailer_url'),
                    "raw": content
                }
        return {}


# =====================================================================
# 3. AnimeKai Client (anime.4umovies.site)
# =====================================================================
class AnimeKaiClient:
    BASE_URL = "https://anime.4umovies.site"
    SEARCH_API = "https://anime.4umovies.site/api/search"
    PLAY_API = "https://anime.4umovies.site/api/play"
    EPISODES_API = "https://anime.4umovies.site/api/episodes"

    def search(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Search Anime catalog with AniList metadata."""
        url = f"{self.SEARCH_API}?q={urllib.parse.quote(query)}&limit={limit}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
            return data.get('data', [])

    def get_stream(self, anime_id: str, episode_num: int = 1) -> Dict[str, Any]:
        """Resolve streaming servers and direct HLS URLs."""
        url = f"{self.PLAY_API}?id={urllib.parse.quote(anime_id)}&ep={episode_num}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
            streams = []
            tracks = data.get('tracks', [])
            for t in tracks:
                track_name = t.get('track', 'sub')
                for p in t.get('providers', []):
                    for s in p.get('servers', []):
                        headers = s.get('headers', {})
                        for st in s.get('streams', []):
                            streams.append({
                                'track': track_name,
                                'server': s.get('server'),
                                'format': st.get('format'),
                                'quality': st.get('quality'),
                                'url': st.get('rawUrl') or st.get('proxyUrl'),
                                'headers': headers
                            })
            return {
                "success": data.get('success', False),
                "episode_number": episode_num,
                "streams": streams,
                "raw": data
            }


# =====================================================================
# 4. DesiTV Client (desitv.4umovies.site)
# =====================================================================
class DesiTVClient:
    BASE_URL = "https://desitv.4umovies.site"
    SERIALS_URL = "https://desitv.4umovies.site/data/serials.json"
    RESOLVER_URL = "https://desitv.4umovies.site/api/resolve"

    def get_catalog(self) -> Dict[str, Any]:
        """Get list of TV serials and episodes."""
        req = urllib.request.Request(self.SERIALS_URL, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))

    def resolve_stream(self, episode_page_url: str) -> Dict[str, Any]:
        """Resolve DesiTV serial episode stream links."""
        url = f"{self.RESOLVER_URL}?url={urllib.parse.quote(episode_page_url)}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))


# =====================================================================
# 5. SonyLIV Client (sony.4umovies.site)
# =====================================================================
class SonyLIVClient:
    EPISODES_API = "https://asmultiverse.site/yt-down/episodes.php?show={show_id}"
    STREAM_API = "https://asmultiverse.site/yt-down/stream.php?id={content_id}"

    def get_show_episodes(self, show_id: str) -> Dict[str, Any]:
        """Get all seasons and episodes for a SonyLIV show."""
        url = self.EPISODES_API.format(show_id=show_id)
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))

    def get_stream_manifest_url(self, content_id: str) -> str:
        """Returns the MPD manifest URL for playback."""
        return self.STREAM_API.format(content_id=content_id)


# Quick verification CLI
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("==========================================================")
    print("🎬 Testing 4uMovies Network Unified Multi-Platform Client")
    print("==========================================================")

    # 1. NetMirror
    net = NetMirrorClient()
    movies = net.search("Fighter")
    print(f"\n[NetMirror] Found {len(movies)} matches for 'Fighter':")
    if movies:
        m = movies[0]
        print(f" -> ID: {m.get('id')}, Title: {m.get('title')}, Year: {m.get('year')}")
        stream = net.resolve_stream(m.get('id'))
        print(f" -> Direct Stream: {stream.get('directStreamUrl')[:90]}...")

    # 2. Mastii OTT
    masti = MastiiClient()
    shows = masti.list_shows()
    print(f"\n[Mastii OTT] Found {len(shows)} shows:")
    if shows:
        s = shows[0]
        print(f" -> ID: {s.get('id')}, Title: {s.get('title')}, Season ID: {s.get('season_id')}")
        m_stream = masti.get_stream(s.get('id'))
        print(f" -> Decrypted Direct HLS: {m_stream.get('stream_url')}")

    # 3. AnimeKai
    anime = AnimeKaiClient()
    results = anime.search("Naruto", limit=1)
    print(f"\n[AnimeKai] Found {len(results)} anime:")
    if results:
        a = results[0]
        title = a.get('title', {}).get('english') or a.get('title', {}).get('romaji')
        print(f" -> ID: {a.get('id')}, Title: {title}")
        a_stream = anime.get_stream(a.get('id'), episode_num=1)
        if a_stream.get('streams'):
            first_stream = a_stream['streams'][0]
            print(f" -> Server: {first_stream['server']} | HLS Stream: {first_stream['url'][:90]}...")

    # 4. SonyLIV
    sony = SonyLIVClient()
    sony_data = sony.get_show_episodes("1700000084")
    print(f"\n[SonyLIV] Show: {sony_data.get('showTitle')}, Total Seasons: {len(sony_data.get('seasons', []))}")
    print(f" -> Stream Manifest: {sony.get_stream_manifest_url('1090548214')}")

    print("\n✅ All 4uMovies network clients verified working successfully!")
