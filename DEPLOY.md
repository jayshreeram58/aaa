# 🚀 Course Wallah Downloader Bot - Deployment Guide

This document outlines deployment instructions for all supported platforms, covering Local Windows/Linux, Cloud Notebooks (Colab, Kaggle, Deepnote, Paperspace), Railway, Render, and Heroku.

---

## 🟣 Target 1: Heroku 1-Click & Container Deployment (Fixed & Recommended)

### Option A: 1-Click Heroku Web Deploy (Easiest)
1. Click the **Deploy to Heroku** button in the [README.md](README.md):
   [![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/ramjipatel-tech/course-wallah-downloader-bot)
2. Enter your credentials in the Heroku web interface:
   - `API_ID`: Your Telegram API ID from [my.telegram.org](https://my.telegram.org)
   - `API_HASH`: Your Telegram API Hash from [my.telegram.org](https://my.telegram.org)
   - `BOT_TOKEN`: Your Telegram Bot Token from [@BotFather](https://t.me/BotFather)
   - `OWNER_ID`: Your numeric Telegram user ID
3. Click **Deploy App**.
4. Heroku automatically:
   - Installs system binaries via `Aptfile` (`ffmpeg`, `aria2`, `fonts`, `libmagic1`).
   - Installs Python 3.11 dependencies via `requirements.txt`.
   - Starts the `web` dyno with `run_heroku.py` (which binds to `$PORT` and starts the bot engine concurrently).
   - Your bot is **ONLINE in Telegram immediately** without any manual scaling or terminal commands!

---

### Option B: Heroku CLI (Standard or Container)
```bash
# 1. Login to Heroku CLI
heroku login

# 2. Create app
heroku create your-bot-name

# 3. Set Config Vars
heroku config:set API_ID=12345678 \
                  API_HASH="your_api_hash" \
                  BOT_TOKEN="your_bot_token" \
                  OWNER_ID=123456789 \
                  WATERMARK_TEXT="Course Wallah"

# 4. Deploy code
git push heroku main

# 5. Verify process is running
heroku ps
heroku logs --tail
```

---

## 🚂 Target 2: Railway Deployment

1. Connect repository on [Railway](https://railway.com).
2. In Railway Service Settings, add a **Volume** mounted at `/data`.
3. Set environment variables: `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`, `CW_STORAGE_DIR=/data`.
4. Deploy service.

---

## ☁️ Target 3: Render Background Worker

1. In Render Dashboard, select **New -> Blueprint**.
2. Connect this repository containing `render.yaml`.
3. Render automatically sets up persistent disk at `/data`.
4. Enter secret environment variables (`API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`).

---

## 🖥 Target 4: Local Windows Deployment

1. **Install FFmpeg** and add to system `PATH`.
2. **Install Dependencies**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Configure `.env`**:
   ```env
   API_ID=12345678
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   OWNER_ID=123456789
   CW_STORAGE_DIR=B:\CourseWallahData
   ```
4. **Run Bot**:
   ```powershell
   python main.py
   ```
