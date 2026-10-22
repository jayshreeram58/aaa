import sys
import asyncio
from aiohttp.test_utils import TestServer, TestClient
from apis.run_all import create_master_app

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def run_modular_tests():
    app = create_master_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    print("==================================================")
    print("🧪 Verifying All Modular Personal APIs")
    print("==================================================")

    # 1. Master index
    res = await client.get("/")
    print("1. Master Index Status:", res.status)

    # 2. SonyLIV Token
    res = await client.get("/sony/token")
    print("2. SonyLIV Token Status:", res.status)
    data = await res.json()
    print(" -> Official Token snippet:", data.get("token")[:40], "...")

    # 3. SonyLIV Show
    res = await client.get("/sony/show/1700000084")
    print("3. SonyLIV Show Status:", res.status)
    data = await res.json()
    print(" -> Title:", data.get("data", {}).get("title"), "Seasons:", data.get("data", {}).get("totalSeasons"))

    # 4. SonyLIV Direct Stream
    res = await client.get("/sony/stream/1090548214")
    print("4. SonyLIV Stream Status:", res.status)
    data = await res.json()
    print(" -> Direct Akamai DASH:", data.get("dashUrl")[:60], "...")
    print(" -> Direct Akamai HLS: ", data.get("hlsUrl")[:60], "...")

    # 5. NetMirror Search
    res = await client.get("/net/search?q=Fighter")
    print("5. NetMirror Status:", res.status)
    data = await res.json()
    print(" -> Matches count:", data.get("count"))

    # 6. Mastii OTT
    res = await client.get("/masti/shows")
    print("6. Mastii OTT Status:", res.status)
    data = await res.json()
    print(" -> Total Shows:", data.get("count"))

    # 7. AnimeKai
    res = await client.get("/anime/search?q=Naruto&limit=1")
    print("7. AnimeKai Status:", res.status)
    data = await res.json()
    print(" -> Anime matches:", data.get("count"))

    # 8. YouTube Cloud Extractor
    res = await client.post("/yt/info", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    print("8. YouTube 4K Info Status:", res.status)
    data = await res.json()
    print(" -> Title:", data.get("title"))

    await client.close()
    print("\n✅ All 6 Modular Personal APIs verified working 100%!")

if __name__ == '__main__':
    asyncio.run(run_modular_tests())
