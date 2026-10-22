#!/usr/bin/env python3
"""
Course Wallah StoryTV Channel Recovery Script
Scans a Telegram Channel for previously uploaded StoryTV videos,
reconstructs the show JSON, and automatically pushes it to GitHub repository (storytv-api).

Usage:
    python recover_storytv_channel.py <TARGET_CHANNEL_ID> [SHOW_ID]

Example:
    python recover_storytv_channel.py -1002233445566 2935
"""

import os
import re
import sys
import json
import time
import asyncio
from pathlib import Path

from pyrogram import Client
from storytv_handler import (
    load_show_json_data,
    save_show_json_data,
    sync_show_to_github,
    fetch_show_episodes_page,
    load_all_catalog_shows
)

BASE_DIR = Path(__file__).resolve().parent

# Read .env credentials
API_ID = 28088290
API_HASH = "6998f2c585fdce65ac72dfa23d02b6ec"
BOT_TOKEN = "8320151161:AAHdJ21rfAylAzKAWNvW5v67M1AwGL17g9E"

# Try loading from .env if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("API_ID="):
                try: API_ID = int(line.split("=", 1)[1].strip().strip('"').strip("'"))
                except: pass
            elif line.startswith("API_HASH="):
                API_HASH = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("BOT_1_TOKEN=") or line.startswith("BOT_TOKEN="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and "your_" not in val:
                    BOT_TOKEN = val

async def scan_and_recover_channel(channel_id: int, target_show_id: str = "2935", max_messages: int = 1500):
    print(f"\n=======================================================")
    print(f"🎬 StoryTV Telegram Channel Scanner & Auto-Push Engine")
    print(f"=======================================================")
    print(f"📢 Target Channel ID: {channel_id}")
    print(f"🆔 Target Show ID:    {target_show_id}")
    print(f"🔍 Message Scan Depth: up to {max_messages} messages")
    print(f"-------------------------------------------------------")

    clean_ch_id = str(channel_id).replace("-100", "")

    # 1. Identify show info from catalog
    catalog = load_all_catalog_shows()
    show_meta = next((s for s in catalog if str(s.get("showId")) == str(target_show_id)), None)
    show_title = show_meta.get("showTitle", f"Show {target_show_id}") if show_meta else f"Show {target_show_id}"
    genre = show_meta.get("genre", "Short Drama") if show_meta else "Short Drama"
    total_eps = int(show_meta.get("totalEpisodes", 0) if show_meta else 0)

    print(f"📺 Found Show: '{show_title}' ({genre}) | Total Episodes in Catalog: {total_eps}")

    # 2. Load existing show JSON (local or GitHub)
    show_obj = load_show_json_data(target_show_id)
    episodes_map = {int(ep["index"]): ep for ep in show_obj.get("episodes", []) if "index" in ep}
    initial_count = len(episodes_map)
    print(f"💾 Already known episodes before scan: {initial_count}")

    # 3. Connect Pyrogram Bot Client
    app = Client("storytv_channel_recovery", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
    await app.start()
    me = await app.get_me()
    print(f"🤖 Connected as @{me.username} (ID: {me.id})")

    # 4. Fetch official stream URLs to match thumbnail / m3u8
    print(f"🌐 Fetching official episode metadata streams...")
    stream_lookup = {}
    cursor = None
    for _ in range(25):  # up to ~750 episodes
        batch = fetch_show_episodes_page(target_show_id, cursor=cursor)
        if not batch:
            break
        for item in batch:
            idx = int(item.get("index", 1))
            stream_lookup[idx] = item
        last_idx = batch[-1].get("index")
        if cursor is not None and last_idx <= cursor:
            break
        cursor = last_idx
    print(f"✅ Cached {len(stream_lookup)} official episode streams for metadata cross-matching")

    # 5. Scan Channel Messages
    print(f"\n📡 Scanning channel message IDs (1 to {max_messages})...")
    recovered = 0

    batch_ids = []
    for mid in range(1, max_messages + 1):
        batch_ids.append(mid)
        if len(batch_ids) >= 100 or mid == max_messages:
            try:
                msgs = await app.get_messages(chat_id=channel_id, message_ids=batch_ids)
                for m in msgs:
                    if not m or not m.video:
                        continue

                    caption = m.caption or ""
                    # Match Show ID and Episode index from caption
                    m_show = re.search(r"Show ID:\s*<code>?(\d+)</code>?", caption, re.IGNORECASE)
                    m_ep = re.search(r"Episode\s*(\d+)", caption, re.IGNORECASE)
                    if not m_ep:
                        m_ep = re.search(r"Episode:\s*(\d+)", caption, re.IGNORECASE)

                    found_show = m_show.group(1) if m_show else target_show_id

                    # If this message belongs to our show and has episode index
                    if found_show == target_show_id and m_ep:
                        ep_idx = int(m_ep.group(1))
                        tg_link = f"https://t.me/c/{clean_ch_id}/{m.id}"
                        file_id = m.video.file_id

                        meta = stream_lookup.get(ep_idx, {})
                        stream_url = meta.get("epsUrl", "")
                        thumb_url = meta.get("thumb", "")

                        if ep_idx not in episodes_map or not episodes_map[ep_idx].get("telegramUrl"):
                            episodes_map[ep_idx] = {
                                "index": ep_idx,
                                "contentId": str(meta.get("contentId", ep_idx)),
                                "title": meta.get("epsTitle", f"{show_title} - Episode {ep_idx}"),
                                "label": f"{ep_idx}/{total_eps or len(episodes_map)}",
                                "telegramMessageId": m.id,
                                "telegramUrl": tg_link,
                                "fileId": file_id,
                                "streamUrl": stream_url,
                                "thumbnail": thumb_url,
                                "status": "uploaded",
                                "recoveredFromChannel": True,
                                "uploadedAt": time.strftime("%Y-%m-%d %H:%M:%S")
                            }
                            recovered += 1
                            if recovered % 25 == 0 or recovered == 1:
                                print(f"  ➜ Recovered #{recovered}: Episode {ep_idx} (Msg #{m.id}) -> {tg_link}")

            except Exception as e:
                print(f"⚠️ Error checking batch: {e}")
            batch_ids = []

    await app.stop()

    print(f"\n=======================================================")
    print(f"✅ Scan Complete! Newly recovered: {recovered} episodes")
    print(f"📊 Total episodes in show record: {len(episodes_map)}/{total_eps or len(episodes_map)}")
    print(f"=======================================================")

    if episodes_map:
        show_obj["showId"] = str(target_show_id)
        show_obj["showTitle"] = show_title
        show_obj["genre"] = genre
        show_obj["totalEpisodes"] = max(total_eps, len(episodes_map))
        show_obj["channelId"] = str(channel_id)
        show_obj["lastUpdated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        show_obj["episodes"] = [episodes_map[k] for k in sorted(episodes_map.keys())]

        # 6. Save locally
        save_show_json_data(target_show_id, show_obj)
        print(f"💾 Saved to local disk: data/shows/{target_show_id}.json")

        # 7. Push to GitHub repository (storytv-api)
        print(f"🚀 Pushing complete show JSON and index to GitHub...")
        synced = sync_show_to_github(target_show_id, show_title, show_obj)
        if synced:
            print(f"🎉 SUCCESS! All {len(episodes_map)} episodes pushed and live on storytv-api GitHub!")
        else:
            print(f"⚠️ Saved locally in data/shows/. Set GITHUB_TOKEN or check git credentials for auto-push.")

    return len(episodes_map)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python recover_storytv_channel.py <CHANNEL_ID> [SHOW_ID]")
        print("Example: python recover_storytv_channel.py -1002233445566 2935")
        sys.exit(1)

    ch_arg = sys.argv[1].strip()
    try:
        ch_id = int(ch_arg)
    except ValueError:
        print(f"Invalid channel ID: {ch_arg}")
        sys.exit(1)

    sh_id = sys.argv[2].strip() if len(sys.argv) > 2 else "2935"
    asyncio.run(scan_and_recover_channel(channel_id=ch_id, target_show_id=sh_id))
