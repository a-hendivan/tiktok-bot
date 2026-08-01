"""
Multi-Platform Video Downloader Telegram Bot
---------------------------------------------
Send the bot a link from TikTok, YouTube, Instagram, or Pinterest and it
replies with the video (no watermark).

Requirements: python-telegram-bot>=20, yt-dlp, python-dotenv
Run:  python bot.py
"""

import os
import re
import logging
import tempfile
import shutil
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import yt_dlp

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()  # reads .env file for BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN not set. Create a .env file (see .env.example) with your token."
    )

# Telegram bots can send files up to 50MB via the normal Bot API.
MAX_FILE_SIZE_MB = 50

# Matches links from any of the supported platforms.
SUPPORTED_URL_PATTERN = re.compile(
    r"(https?://"
    r"(?:"
    r"(?:www\.|vm\.|vt\.|m\.)?tiktok\.com"
    r"|(?:www\.|m\.)?youtube\.com|youtu\.be"
    r"|(?:www\.)?instagram\.com"
    r"|(?:www\.)?pinterest\.(?:com|co\.uk|ca|de|fr|jp)|pin\.it"
    r")"
    r"/\S+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def download_video(url: str, download_dir: str) -> str:
    """
    Downloads a video (watermark-free where applicable) using yt-dlp.
    Works for TikTok, YouTube, Instagram, and Pinterest links — yt-dlp
    picks the right extractor automatically based on the URL.
    Returns the path to the downloaded file.
    Raises an exception if the download fails.
    """
    output_template = os.path.join(download_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        # Cap quality so we don't pull down huge YouTube 4K files that will
        # just get rejected by Telegram's 50MB limit anyway.
        "format": "mp4[filesize<50M]/best[filesize<50M]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # yt-dlp pulls TikTok's/Instagram's clean (no-watermark) rendition
        # by default — it hits each platform's API directly rather than
        # scraping the rendered page.
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
        return filepath


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Send me a link from TikTok, YouTube, Instagram, or Pinterest "
        "and I'll download the video for you, watermark-free."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    match = SUPPORTED_URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "That doesn't look like a supported link. Send me a URL from "
            "TikTok, YouTube, Instagram, or Pinterest."
        )
        return

    url = match.group(1)
    status_msg = await update.message.reply_text("⏬ Downloading...")
    await update.effective_chat.send_action(ChatAction.UPLOAD_VIDEO)

    # Use a fresh temp directory per request so files never collide or linger.
    tmp_dir = tempfile.mkdtemp(prefix="video_")
    try:
        filepath = download_video(url, tmp_dir)

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"⚠️ Video is {size_mb:.1f}MB, which is over Telegram's "
                f"{MAX_FILE_SIZE_MB}MB bot upload limit. Can't send it."
            )
            return

        with open(filepath, "rb") as video_file:
            await update.message.reply_video(video=video_file)

        await status_msg.delete()

    except Exception as exc:
        logger.exception("Failed to download %s", url)
        await status_msg.edit_text(
            "❌ Couldn't download that video. This can happen if:\n"
            "• The post is private (Instagram in particular needs login for that)\n"
            "• The platform changed something and yt-dlp needs an update\n"
            "• The link itself is invalid\n\n"
            f"Details: {exc}"
        )
    finally:
        # Always clean up temp files, success or failure.
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
