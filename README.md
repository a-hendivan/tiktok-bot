# Multi-Platform Video Downloader Telegram Bot

A personal Telegram bot that downloads videos (watermark-free) from **TikTok, YouTube, Instagram, and Pinterest** when you send it a link.

## Features
- Supports TikTok, YouTube, Instagram, and Pinterest links
- Watermark-free downloads via `yt-dlp`
- Auto-deletes temp files after sending
- Warns you if a video is too large for Telegram's 50MB bot upload limit

## Platform notes
- **TikTok** — watermark-free by default, no login needed for public videos.
- **YouTube** — works for public videos/Shorts. Quality is auto-capped to try to stay under Telegram's 50MB limit; very long videos may still get rejected.
- **Instagram** — works for public posts/Reels. Private accounts or posts require login cookies, which this basic setup doesn't include (ask me if you want that added).
- **Pinterest** — works for public pins with video content.

---

## 1. Prerequisites

- Python 3.10+ installed (`python3 --version` to check)
- A Telegram account
- Git installed (`git --version` to check)

---

## 2. Get a bot token from BotFather

1. Open Telegram, search for **@BotFather**.
2. Send `/newbot`.
3. Give it a name and a username (must end in `bot`, e.g. `my_tiktok_dl_bot`).
4. BotFather replies with an API token like `123456789:AAExampleTokenString`. Copy it — you'll need it in step 4.

---

## 3. Set up the project locally

```bash
# Create and enter the project folder
mkdir tiktok-bot && cd tiktok-bot

# (files from this project go here — bot.py, requirements.txt, etc.)

# Create a virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## 4. Add your bot token

```bash
cp .env.example .env
```

Open `.env` and paste your real token:

```
BOT_TOKEN=123456789:AAExampleTokenString
```

`.env` is already listed in `.gitignore` so it will never get committed or pushed to GitHub.

---

## 5. Run it

```bash
python bot.py
```

You should see `Bot starting...` in the terminal. Open Telegram, find your bot by its username, send `/start`, then paste a TikTok link. It should reply with the video.

Stop it anytime with `Ctrl+C`.

---

## 6. Git integration

Initialize a repo and make your first commit:

```bash
git init
git add .
git commit -m "Initial commit: TikTok downloader bot"
```

### Push to GitHub

1. Create a new empty repository on GitHub (no README/license, so it stays empty).
2. Connect and push:

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tiktok-bot.git
git push -u origin main
```

Because `.env` is gitignored, your token stays private — only `.env.example` (the empty template) gets pushed.

### Day-to-day workflow

```bash
git add .
git commit -m "Describe your change"
git push
```

---

## 7. (Optional) Keep it running 24/7 for free

Right now the bot only runs while your terminal is open. To have it always on:

**Option A — Oracle Cloud Free Tier (recommended, free forever)**
1. Create an Always Free VM instance.
2. SSH in, install Python/Git, clone your repo, repeat steps 3–5 above.
3. Use `tmux` or a `systemd` service so it keeps running after you disconnect:
   ```bash
   tmux new -s tiktokbot
   python bot.py
   # Ctrl+B then D to detach; tmux attach -t tiktokbot to reattach
   ```

**Option B — Fly.io free tier** — works well if you'd rather containerize it (ask me and I can add a `Dockerfile`).

**Option C — Raspberry Pi** at home, same steps as A, no cloud account needed.

---

## 8. Keeping it working

TikTok occasionally changes things that break scrapers. If downloads start failing, first try updating yt-dlp:

```bash
pip install -U yt-dlp
```

This alone fixes the vast majority of breakage, usually within days of a TikTok change.

---

## Project structure

```
tiktok-bot/
├── bot.py            # main bot logic
├── requirements.txt  # dependencies
├── .env.example       # template for your token (safe to commit)
├── .env               # your real token (never commit — gitignored)
├── .gitignore
└── README.md
```
