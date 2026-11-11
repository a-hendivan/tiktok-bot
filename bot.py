"""
Multi-Platform Video Downloader + Audio Extractor Telegram Bot
-----------------------------------------------------------------
- Send a link from TikTok, YouTube, Instagram, or Pinterest -> choose video or audio (mp3).
- Send/forward an actual video file -> get just the audio (mp3) back.

Requirements: python-telegram-bot>=20, yt-dlp, python-dotenv, ffmpeg (system install)
Run:  python bot.py
"""

import asyncio
import os
import re
import sys
import logging
import tempfile
import urllib.request
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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

# Telegram caps how large a file a standard bot can *download* (not send) at 20MB.
MAX_INCOMING_FILE_SIZE_MB = 20

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# If yt-dlp returns only one of these for a TikTok link, it was a photo post
# (yt-dlp only fetches the background music for those).
AUDIO_ONLY_EXTENSIONS = {".mp3", ".m4a", ".aac", ".opus"}

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


def is_tiktok(url: str) -> bool:
    return "tiktok.com" in url.lower()


def _natural_key(path: Path):
    """Sort 'img_2' before 'img_10' so carousel order is preserved."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name)]


def download_images(url: str, download_dir: str) -> list[str]:
    """
    Downloads every image from a TikTok photo carousel using gallery-dl
    (yt-dlp can't do this). Returns image paths in carousel order.
    """
    result = subprocess.run(
        [sys.executable, "-m", "gallery_dl", "-d", download_dir, url],
        capture_output=True,
        text=True,
        timeout=120,
    )

    images = sorted(
        (p for p in Path(download_dir).rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS),
        key=_natural_key,
    )
    if not images:
        raise RuntimeError(
            "No images found in that post. "
            f"gallery-dl said: {(result.stderr or result.stdout)[-300:]}"
        )
    return [str(p) for p in images]


def download_audio(url: str, download_dir: str) -> str:
    """
    Downloads just the audio from a platform link as an mp3 (needs ffmpeg).
    Returns the path to the mp3 file.
    """
    output_template = os.path.join(download_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # After post-processing the extension becomes .mp3
        return str(Path(ydl.prepare_filename(info)).with_suffix(".mp3"))


def extract_audio(video_path: str) -> str:
    """
    Extracts the audio track from a local video file using ffmpeg.
    Returns the path to the resulting .mp3 file.
    Raises an exception if ffmpeg fails or isn't installed.
    """
    audio_path = str(Path(video_path).with_suffix(".mp3"))

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",  # overwrite output if it exists
            "-i", video_path,
            "-vn",  # strip video, keep audio only
            "-acodec", "libmp3lame",
            "-q:a", "2",  # ~192kbps, good quality
            audio_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")

    return audio_path


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 I can do two things:\n\n"
        "1️⃣ Send me a link from TikTok, YouTube, Instagram, or Pinterest "
        "and choose Video (watermark-free) or Audio (mp3).\n\n"
        "2️⃣ Send/forward an actual video file from your library and I'll "
        f"send back just the audio as an mp3 (up to {MAX_INCOMING_FILE_SIZE_MB}MB)."
    )


async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles a video sent directly to the bot (from the user's own library)."""
    video = update.message.video or update.message.document

    if video.file_size and video.file_size > MAX_INCOMING_FILE_SIZE_MB * 1024 * 1024:
        await update.message.reply_text(
            f"⚠️ That file is over Telegram's {MAX_INCOMING_FILE_SIZE_MB}MB "
            "limit for what bots can download. Try a shorter clip or compress it first."
        )
        return

    status_msg = await update.message.reply_text("🎧 Extracting audio...")
    await update.effective_chat.send_action(ChatAction.UPLOAD_VOICE)

    tmp_dir = tempfile.mkdtemp(prefix="audio_")
    try:
        tg_file = await context.bot.get_file(video.file_id)
        video_path = os.path.join(tmp_dir, "input.mp4")
        await tg_file.download_to_drive(video_path)

        audio_path = extract_audio(video_path)

        with open(audio_path, "rb") as audio_file:
            await update.message.reply_audio(audio=audio_file)

        await status_msg.delete()

    except Exception as exc:
        logger.exception("Failed to extract audio")
        await status_msg.edit_text(
            "❌ Couldn't extract audio from that file.\n\n"
            f"Details: {exc}"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def resolve_url(url: str) -> str:
    """Follows redirects (e.g. vm.tiktok.com short links) and returns the final URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.geturl()
    except Exception:
        return url


async def send_images(context: ContextTypes.DEFAULT_TYPE, chat_id: int, images: list[str]) -> None:
    """Sends each image as its own message."""
    for img in images:
        with open(img, "rb") as f:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=f)
            except Exception:
                # e.g. too large/odd dimensions for a photo: send as a file instead
                f.seek(0)
                await context.bot.send_document(chat_id=chat_id, document=f)
        await asyncio.sleep(0.5)  # stay under Telegram's flood limits


async def handle_photo_post(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    """Downloads and sends all images of a TikTok photo carousel, no questions asked."""
    status_msg = await update.message.reply_text("🖼 Photo post detected, downloading images...")
    tmp_dir = tempfile.mkdtemp(prefix="photos_")
    try:
        images = await asyncio.to_thread(download_images, url, tmp_dir)
        await send_images(context, update.effective_chat.id, images)
        await status_msg.delete()
    except Exception as exc:
        logger.exception("Failed to download photo post %s", url)
        await status_msg.edit_text(f"❌ Couldn't download the images.\n\nDetails: {exc}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User sent text. If it has a supported link, ask video or audio."""
    text = update.message.text or ""
    match = SUPPORTED_URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "That doesn't look like a supported link. Send me a URL from "
            "TikTok, YouTube, Instagram, or Pinterest."
        )
        return

    url = match.group(1)

    # TikTok photo carousels: skip the video/audio question and send the images.
    if is_tiktok(url):
        final_url = await asyncio.to_thread(resolve_url, url)
        if "/photo/" in final_url:
            await handle_photo_post(update, context, final_url)
            return

    # Callback data is limited to 64 bytes, so keep the URL in memory instead.
    context.user_data["pending_url"] = url

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🎬 Video", callback_data="video"),
            InlineKeyboardButton("🎵 Audio (mp3)", callback_data="audio"),
        ]]
    )
    await update.message.reply_text("What do you want to download?", reply_markup=keyboard)


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when the user taps the Video or Audio button."""
    query = update.callback_query
    await query.answer()

    url = context.user_data.get("pending_url")
    if not url:
        await query.edit_message_text("That request expired. Please send the link again.")
        return

    choice = query.data  # "video" or "audio"
    await query.edit_message_text("⏬ Downloading...")
    await update.effective_chat.send_action(
        ChatAction.UPLOAD_VIDEO if choice == "video" else ChatAction.UPLOAD_VOICE
    )

    tmp_dir = tempfile.mkdtemp(prefix="dl_")
    try:
        images = None
        filepath = None

        if choice == "audio":
            filepath = download_audio(url, tmp_dir)
        elif is_tiktok(url) and "/photo/" in url:
            images = download_images(url, tmp_dir)
        else:
            try:
                filepath = download_video(url, tmp_dir)
            except Exception as video_exc:
                if not is_tiktok(url):
                    raise
                # yt-dlp failed on a TikTok link: it may be a photo carousel.
                logger.info("Video download failed, trying as photo post")
                try:
                    images = download_images(url, tmp_dir)
                except Exception:
                    raise video_exc
            else:
                if is_tiktok(url) and Path(filepath).suffix.lower() in AUDIO_ONLY_EXTENSIONS:
                    # Photo post: yt-dlp only grabbed the music.
                    images = download_images(url, tmp_dir)
                    filepath = None

        if images:
            chat_id = update.effective_chat.id
            await query.edit_message_text(f"🖼 Sending {len(images)} image(s)...")
            await send_images(context, chat_id, images)
            await query.delete_message()
            return

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            await query.edit_message_text(
                f"⚠️ File is {size_mb:.1f}MB, over Telegram's {MAX_FILE_SIZE_MB}MB "
                "bot upload limit. Can't send it."
            )
            return

        with open(filepath, "rb") as f:
            if choice == "video":
                await context.bot.send_video(chat_id=update.effective_chat.id, video=f)
            else:
                await context.bot.send_audio(chat_id=update.effective_chat.id, audio=f)

        await query.delete_message()

    except Exception as exc:
        logger.exception("Failed to download %s", url)
        await query.edit_message_text(
            "❌ Couldn't download that. This can happen if:\n"
            "• The post is private (Instagram needs login for that)\n"
            "• The platform changed something and yt-dlp needs an update\n"
            "• ffmpeg isn't installed (needed for audio)\n"
            "• gallery-dl isn't installed (needed for photo posts)\n\n"
            f"Details: {exc}"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_choice, pattern="^(video|audio)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video_file)
    )

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
