"""
Telegram Bot Handler for 4uMovies Network Multi-Platform Streaming & Downloader
Commands:
- /netmirror or /net <movie/series name or ID>
- /mastii or /masti <show name or ID>
- /anime <anime name or ID>
- /sony <show_id>
"""

import os
import re
import asyncio
import logging
from typing import Optional
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from fourmovies_network import (
    NetMirrorClient,
    MastiiClient,
    AnimeKaiClient,
    SonyLIVClient
)

logger = logging.getLogger(__name__)

net_client = NetMirrorClient()
masti_client = MastiiClient()
anime_client = AnimeKaiClient()
sony_client = SonyLIVClient()


async def netmirror_cmd(client: Client, message: Message):
    """Handle /netmirror or /net search and stream resolve."""
    args = message.text.split(None, 1)
    if len(args) < 2:
        return await message.reply_text(
            "🎬 **NetMirror Downloader & Stream Resolver**\n\n"
            "Usage:\n"
            "• `/net <movie or series name>` (e.g. `/net Fighter`)\n"
            "• `/net <content_id>` (e.g. `/net 81698397`)\n\n"
            "⚡ Provides direct 1080p HLS `.m3u8` master streams and multi-subtitles.",
            parse_mode=enums.ParseMode.MARKDOWN
        )

    query = args[1].strip()
    status_msg = await message.reply_text(f"🔍 Searching NetMirror for **{query}**...", parse_mode=enums.ParseMode.MARKDOWN)

    try:
        # Check if direct ID
        if query.isdigit():
            stream = await asyncio.to_thread(net_client.resolve_stream, query)
            if stream and stream.get('success'):
                title = stream.get('title', f"Item {query}")
                is_series = stream.get('isSeries', False)
                direct_url = stream.get('directStreamUrl') or stream.get('streamUrl')
                episodes = stream.get('episodes', [])

                text = (
                    f"🎬 **{title}**\n\n"
                    f"• **Type:** {'TV Series' if is_series else 'Movie'}\n"
                    f"• **ID:** `{query}`\n"
                )
                if episodes:
                    text += f"• **Total Episodes:** {len(episodes)}\n\n"
                    text += "To resolve a specific episode:\n`/net " + f"{query} <ep_id>`"
                else:
                    text += f"\n🍿 **Direct 1080p Stream URL:**\n`{direct_url}`"

                buttons = []
                if direct_url:
                    buttons.append([InlineKeyboardButton("▶️ Stream Stream (Web/VLC)", url=direct_url)])

                reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
                return await status_msg.edit_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.MARKDOWN)

        # Search by title
        results = await asyncio.to_thread(net_client.search, query)
        if not results:
            return await status_msg.edit_text(f"❌ No movies or series found matching: **{query}**", parse_mode=enums.ParseMode.MARKDOWN)

        # If exactly 1 match, auto-resolve
        if len(results) == 1:
            item = results[0]
            item_id = str(item.get('id'))
            stream = await asyncio.to_thread(net_client.resolve_stream, item_id)
            title = item.get('title') or stream.get('title')
            year = item.get('year', '')
            direct_url = stream.get('directStreamUrl') or stream.get('streamUrl')

            text = (
                f"🎬 **{title}** ({year})\n\n"
                f"• **Rating:** ⭐ {item.get('vote_average', 'N/A')}\n"
                f"• **Genres:** {', '.join(item.get('genres', []))}\n"
                f"• **NetMirror ID:** `{item_id}`\n\n"
                f"🍿 **Direct 1080p Stream URL:**\n`{direct_url}`"
            )
            buttons = [[InlineKeyboardButton("▶️ Open Stream", url=direct_url)]]
            return await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

        # Multiple matches
        text = f"🍿 **Found {len(results)} matches for '{query}':**\n\n"
        buttons = []
        for it in results[:8]:
            it_id = str(it.get('id'))
            it_title = it.get('title', 'Unknown')
            it_year = it.get('year', '')
            text += f"• **{it_title}** ({it_year}) — ID: `{it_id}`\n"
            buttons.append([InlineKeyboardButton(f"▶️ {it_title[:25]} ({it_year})", callback_data=f"net_res_{it_id}")])

        text += "\n_Click a button below or run `/net <id>` to get the direct stream!_"
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception("NetMirror error")
        await status_msg.edit_text(f"❌ Error querying NetMirror: `{e}`")


async def mastii_cmd(client: Client, message: Message):
    """Handle /mastii search and stream resolve."""
    args = message.text.split(None, 1)
    if len(args) < 2:
        return await message.reply_text(
            "👑 **Mastii OTT Pro - Web Series & Originals**\n\n"
            "Usage:\n"
            "• `/mastii <show name>` (e.g. `/mastii Officepur`)\n"
            "• `/mastii <content_id>` (e.g. `/mastii 201364`)\n\n"
            "⚡ Features direct AES-decrypted master HLS streams.",
            parse_mode=enums.ParseMode.MARKDOWN
        )

    query = args[1].strip()
    status_msg = await message.reply_text(f"🔍 Searching Mastii OTT for **{query}**...", parse_mode=enums.ParseMode.MARKDOWN)

    try:
        # Check if direct ID
        if query.isdigit():
            stream_info = await asyncio.to_thread(masti_client.get_stream, query)
            if stream_info and stream_info.get('stream_url'):
                text = (
                    f"👑 **Mastii OTT: {stream_info.get('title')}**\n\n"
                    f"• **ID:** `{query}`\n"
                    f"• **Duration:** {stream_info.get('duration', 'N/A')} mins\n\n"
                    f"🍿 **Direct Master HLS (.m3u8):**\n`{stream_info.get('stream_url')}`"
                )
                buttons = [[InlineKeyboardButton("▶️ Play Stream", url=stream_info.get('stream_url'))]]
                return await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

        # Search shows list
        shows = await asyncio.to_thread(masti_client.list_shows)
        q = query.lower()
        matched = [s for s in shows if q in s.get('title', '').lower()]

        if not matched:
            return await status_msg.edit_text(f"❌ No Mastii OTT shows found matching: **{query}**", parse_mode=enums.ParseMode.MARKDOWN)

        if len(matched) == 1:
            show = matched[0]
            show_id = str(show.get('id'))
            season_id = str(show.get('season_id', ''))
            
            # Get episodes
            eps = await asyncio.to_thread(masti_client.get_season_episodes, season_id)
            stream_info = await asyncio.to_thread(masti_client.get_stream, show_id)
            stream_url = stream_info.get('stream_url', '')

            text = (
                f"👑 **{show.get('title')}**\n\n"
                f"• **Show ID:** `{show_id}`\n"
                f"• **Season ID:** `{season_id}`\n"
                f"• **Total Episodes:** {len(eps)}\n\n"
                f"🍿 **Master HLS Stream URL:**\n`{stream_url}`"
            )
            buttons = []
            if stream_url:
                buttons.append([InlineKeyboardButton("▶️ Play Episode 1", url=stream_url)])
            return await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None, parse_mode=enums.ParseMode.MARKDOWN)

        # Multiple matches
        text = f"👑 **Found {len(matched)} shows on Mastii OTT:**\n\n"
        buttons = []
        for s in matched[:8]:
            s_id = str(s.get('id'))
            s_title = s.get('title', 'Unknown')
            text += f"• **{s_title}** — ID: `{s_id}`\n"
            buttons.append([InlineKeyboardButton(f"👑 {s_title[:25]}", callback_data=f"masti_res_{s_id}")])

        text += "\n_Click a show above to resolve its episodes & stream!_"
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception("Mastii error")
        await status_msg.edit_text(f"❌ Error querying Mastii OTT: `{e}`")


async def anime_cmd(client: Client, message: Message):
    """Handle /anime search and stream resolve."""
    args = message.text.split(None, 1)
    if len(args) < 2:
        return await message.reply_text(
            "🌸 **AnimeKai Stream Resolver**\n\n"
            "Usage:\n"
            "• `/anime <anime title>` (e.g. `/anime Naruto` or `/anime Attack on Titan`)\n\n"
            "⚡ Features multi-server HD HLS streaming with Sub & Dub tracks.",
            parse_mode=enums.ParseMode.MARKDOWN
        )

    query = args[1].strip()
    status_msg = await message.reply_text(f"🔍 Searching Anime for **{query}**...", parse_mode=enums.ParseMode.MARKDOWN)

    try:
        results = await asyncio.to_thread(anime_client.search, query, limit=5)
        if not results:
            return await status_msg.edit_text(f"❌ No anime found matching: **{query}**")

        text = f"🌸 **Found {len(results)} matches for '{query}':**\n\n"
        buttons = []
        for a in results:
            a_id = a.get('id')
            t_obj = a.get('title', {})
            title = t_obj.get('english') or t_obj.get('romaji') or 'Anime'
            year = a.get('season_year', '')
            eps = a.get('episode_count', '?')
            text += f"• **{title}** ({year}) — Episodes: {eps}\n"
            buttons.append([InlineKeyboardButton(f"▶️ {title[:25]}", callback_data=f"anime_res_{a_id}")])

        text += "\n_Click an anime to resolve Episode 1 stream!_"
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception("Anime error")
        await status_msg.edit_text(f"❌ Error querying AnimeKai: `{e}`")


async def fourmovies_callback_handler(client: Client, callback: CallbackQuery):
    """Handle inline button clicks for NetMirror, Mastii, and Anime."""
    data = callback.data
    try:
        if data.startswith("net_res_"):
            content_id = data.split("net_res_")[1]
            await callback.answer("Resolving NetMirror stream...", show_alert=False)
            stream = await asyncio.to_thread(net_client.resolve_stream, content_id)
            title = stream.get('title', 'Movie')
            direct_url = stream.get('directStreamUrl') or stream.get('streamUrl')

            text = (
                f"🎬 **{title}**\n\n"
                f"• **ID:** `{content_id}`\n\n"
                f"🍿 **Direct 1080p Stream URL:**\n`{direct_url}`"
            )
            buttons = [[InlineKeyboardButton("▶️ Open Stream", url=direct_url)]]
            await callback.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

        elif data.startswith("masti_res_"):
            content_id = data.split("masti_res_")[1]
            await callback.answer("Decrypting Mastii OTT stream...", show_alert=False)
            stream_info = await asyncio.to_thread(masti_client.get_stream, content_id)
            text = (
                f"👑 **Mastii OTT: {stream_info.get('title')}**\n\n"
                f"• **ID:** `{content_id}`\n\n"
                f"🍿 **Master HLS Stream URL:**\n`{stream_info.get('stream_url')}`"
            )
            buttons = [[InlineKeyboardButton("▶️ Play Stream", url=stream_info.get('stream_url'))]]
            await callback.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)

        elif data.startswith("anime_res_"):
            anime_id = data.split("anime_res_")[1]
            await callback.answer("Fetching anime stream servers...", show_alert=False)
            stream_info = await asyncio.to_thread(anime_client.get_stream, anime_id, episode_num=1)
            streams = stream_info.get('streams', [])
            if streams:
                first = streams[0]
                text = (
                    f"🌸 **Anime Episode 1 Stream**\n\n"
                    f"• **Server:** {first.get('server')}\n"
                    f"• **Track:** {first.get('track')}\n\n"
                    f"🍿 **HLS Stream URL:**\n`{first.get('url')}`"
                )
                buttons = [[InlineKeyboardButton("▶️ Stream Now", url=first.get('url'))]]
                await callback.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.MARKDOWN)
            else:
                await callback.message.reply_text("❌ No active streaming servers found for this anime.")

    except Exception as e:
        logger.exception("4uMovies callback error")
        await callback.message.reply_text(f"❌ Callback Error: `{e}`")
