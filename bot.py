"""
TikTok Downloader Telegram Bot
--------------------------------
Send the bot a TikTok link and it replies with the watermark-free video.

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

TIKTOK_URL_PATTERN = re.compile(
    r"(https?://(?:www\.|vm\.|vt\.|m\.)?tiktok\.com/\S+)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def download_tiktok(url: str, download_dir: str) -> str:
    """
    Downloads a TikTok video (watermark-free) using yt-dlp.
    Returns the path to the downloaded file.
    Raises an exception if the download fails.
    """
    output_template = os.path.join(download_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "mp4/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # yt-dlp pulls TikTok's clean (no-watermark) rendition by default.
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
        "👋 Send me a TikTok link and I'll download it for you, watermark-free."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    match = TIKTOK_URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "That doesn't look like a TikTok link. Send me a tiktok.com URL."
        )
        return

    url = match.group(1)
    status_msg = await update.message.reply_text("⏬ Downloading...")
    await update.effective_chat.send_action(ChatAction.UPLOAD_VIDEO)

    # Use a fresh temp directory per request so files never collide or linger.
    tmp_dir = tempfile.mkdtemp(prefix="tiktok_")
    try:
        filepath = download_tiktok(url, tmp_dir)

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
            "❌ Couldn't download that video. TikTok may have changed something, "
            "or the link is private/invalid.\n\n"
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
