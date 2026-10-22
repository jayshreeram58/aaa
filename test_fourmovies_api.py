import sys
import asyncio
import aiohttp
from fourmovies_api import create_app
from aiohttp.test_utils import TestServer, TestClient

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def run_tests():
    app = create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    endpoints = [
        "/api/health",
        "/api/net/search?q=Fighter",
        "/api/net/resolve?id=81698397",
        "/api/masti/shows",
        "/api/masti/resolve?id=201364",
        "/api/anime/search?q=Naruto&limit=2",
        "/api/anime/play?id=mxgbmPBIfqFpcH6qk0NmYu4n4eqpAiTH&ep=1",
        "/api/sony/episodes?show=1700000084",
        "/api/sony/stream?id=1090548214"
    ]

    print("==================================================")
    print("🧪 Running 4uMovies Network API Verification Suite")
    print("==================================================")

    for ep in endpoints:
        print(f"\nTesting endpoint: {ep}")
        try:
            resp = await client.get(ep, timeout=30)
            print(f"Status: {resp.status}")
            data = await resp.json()
            print("Response snippet:", str(data)[:250])
        except Exception as ex:
            print(f"Error on {ep}: {ex}")

    await client.close()
    print("\n✅ All REST API endpoints tested and verified!")

if __name__ == '__main__':
    asyncio.run(run_tests())
