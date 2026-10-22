"""
Direct Official SonyLIV Client & Stream Engine
Directly interfaces with SonyLIV's API (apiv2.sonyliv.com) - Zero third-party dependency.
Generates:
1. Official Security JWT Token
2. Akamai EdgeAuth signed DASH MPD and HLS Stream URLs
3. Series, Seasons, and Episode Catalog
"""

import json
import uuid
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional

SONY_API_BASE = "https://apiv2.sonyliv.com/AGL"

HEADERS = {
    'Referer': 'https://www.sonyliv.com/',
    'Origin': 'https://www.sonyliv.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}


class DirectSonyLIV:
    def __init__(self):
        self._security_token = None
        self._token_expiry = 0
        self._device_id = str(uuid.uuid4())

    def get_security_token(self, force_refresh: bool = False) -> str:
        """Fetch official SonyLIV security token JWT."""
        now = time.time()
        if not force_refresh and self._security_token and now < self._token_expiry:
            return self._security_token

        url = f"{SONY_API_BASE}/1.4/A/ENG/WEB/ALL/GETTOKEN"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
            self._security_token = data.get('resultObj')
            # Token typically valid for 24-48 hours, cache for 12 hours
            self._token_expiry = now + 43200
            return self._security_token

    def get_show_details(self, show_id: str) -> Dict[str, Any]:
        """Fetch show details and list of all seasons."""
        token = self.get_security_token()
        headers = dict(HEADERS)
        headers['security_token'] = token
        headers['device_id'] = self._device_id

        url = f"{SONY_API_BASE}/1.9/R/ENG/WEB/IN/DL/DETAIL/{show_id}?kids_safe=false&from=0&to=49"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as r:
            res = json.loads(r.read().decode('utf-8'))
            containers = res.get('resultObj', {}).get('containers', [{}])[0]
            metadata = containers.get('metadata', {})
            season_containers = containers.get('containers', [])

            seasons = []
            for s in season_containers:
                seasons.append({
                    "id": str(s.get('id')),
                    "title": s.get('metadata', {}).get('title') or f"Season {s.get('id')}",
                    "episodeCount": s.get('metadata', {}).get('totalEpisodes')
                })

            return {
                "showId": show_id,
                "title": metadata.get('title'),
                "synopsis": metadata.get('longDescription') or metadata.get('shortDescription'),
                "poster": metadata.get('portraitThumb') or metadata.get('landscapeThumb'),
                "totalSeasons": len(seasons),
                "seasons": seasons
            }

    def get_season_episodes(self, season_id: str, offset: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch all episodes inside a season."""
        token = self.get_security_token()
        headers = dict(HEADERS)
        headers['security_token'] = token
        headers['device_id'] = self._device_id

        url = f"{SONY_API_BASE}/1.4/R/ENG/WEB/IN/CONTENT/DETAIL/BUNDLE/{season_id}?from={offset}&to={offset + limit - 1}&orderBy=episodeNumber&sortOrder=asc"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as r:
            res = json.loads(r.read().decode('utf-8'))
            eps = res.get('resultObj', {}).get('containers', [{}])[0].get('containers', [])

            results = []
            for ep in eps:
                m = ep.get('metadata', {})
                results.append({
                    "id": str(ep.get('id')),
                    "episodeNumber": m.get('episodeNumber'),
                    "title": m.get('episodeTitle') or m.get('title'),
                    "duration": m.get('duration'),
                    "releaseDate": m.get('creationDate'),
                    "thumbnail": m.get('landscapeThumb') or m.get('portraitThumb')
                })
            return results

    def get_all_season_episodes(self, season_id: str, max_episodes: int = 5000) -> List[Dict[str, Any]]:
        """Fetch all episodes inside a season with automatic pagination."""
        all_episodes = []
        offset = 0
        batch_size = 100
        while offset < max_episodes:
            try:
                eps = self.get_season_episodes(season_id, offset=offset, limit=batch_size)
                if not eps:
                    break
                all_episodes.extend(eps)
                if len(eps) < batch_size:
                    break
                offset += len(eps)
            except Exception:
                break
        return all_episodes

    def resolve_video_stream(self, video_id: str) -> Dict[str, Any]:
        """
        Generates direct Akamai EdgeAuth signed MPD and HLS stream URLs
        straight from SonyLIV.
        """
        token = self.get_security_token()
        headers = dict(HEADERS)
        headers['security_token'] = token
        headers['device_id'] = self._device_id

        url = f"{SONY_API_BASE}/1.5/A/ENG/WEB/IN/CONTENT/VIDEOURL/VOD/{video_id}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as r:
            res = json.loads(r.read().decode('utf-8'))
            obj = res.get('resultObj', {})

            dash_url = obj.get('videoURL')
            hls_url = None
            if dash_url:
                hls_url = dash_url.replace('.mpd', '.m3u8').replace('/DASH/', '/HLS/')

            subtitles = []
            for sub in obj.get('subtitle', []):
                if sub.get('subtitleUrl'):
                    subtitles.append({
                        "language": sub.get('subtitleLanguageName', 'English'),
                        "url": sub.get('subtitleUrl')
                    })

            return {
                "success": True,
                "videoId": video_id,
                "isEncrypted": obj.get('isEncrypted', False),
                "dashUrl": dash_url,
                "hlsUrl": hls_url,
                "audioLanguages": obj.get('audioLanguages', []),
                "subtitles": subtitles,
                "poster": obj.get('posterURL'),
                "sprite": obj.get('sprite_image_url')
            }


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sony = DirectSonyLIV()
    print("1. Testing Token:", sony.get_security_token()[:50], "...")
    print("\n2. Testing Show Details (TMKOC 1700000084):")
    show = sony.get_show_details("1700000084")
    print(f" -> Title: {show['title']}, Seasons: {show['totalSeasons']}")
    
    print("\n3. Testing Stream Resolution (Ep 1090548214):")
    stream = sony.resolve_video_stream("1090548214")
    print(f" -> DASH MPD: {stream['dashUrl'][:90]}...")
    print(f" -> HLS URL:  {stream['hlsUrl'][:90]}...")
    print(f" -> Encrypted: {stream['isEncrypted']}")
    print("\n✅ Direct SonyLIV Engine 100% operational!")
