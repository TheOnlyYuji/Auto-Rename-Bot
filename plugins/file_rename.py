import os
import re
import time
import shutil
import asyncio
import logging
from datetime import datetime
from PIL import Image
from pyrogram import Client, filters
from plugins.antinsfw import check_anti_nsfw
from helper.utils import progress_for_pyrogram
from helper.database import codeflixbots

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= GLOBALS =================
renaming_operations = {}

# ================= PATTERNS =================
SEASON_EPISODE_PATTERNS = [
    (re.compile(r'S(\d+)(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[\s-]*(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'Season\s*(\d+)\s*Episode\s*(\d+)', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'\[S(\d+)\]\[E(\d+)\]'), ('season', 'episode')),
    (re.compile(r'S(\d+)[^\d]*(\d+)'), ('season', 'episode')),
    (re.compile(r'(?:E|EP|Episode)\s*(\d+)', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\b(\d+)\b'), (None, 'episode'))
]

QUALITY_PATTERNS = [
    (re.compile(r'\b(\d{3,4}[pi])\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(4k|2160p)\b', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\b(2k|1440p)\b', re.IGNORECASE), lambda m: "2k"),
    (re.compile(r'\b(HDRip|HDTV)\b', re.IGNORECASE), lambda m: m.group(1)),
]

# ================= HELPERS =================
def extract_season_episode(filename):
    for pattern, (s, e) in SEASON_EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            season = match.group(1) if s else None
            episode = match.group(2) if e else match.group(1)
            return season, episode
    return None, None


def extract_quality(filename):
    for pattern, extractor in QUALITY_PATTERNS:
        match = pattern.search(filename)
        if match:
            return extractor(match)
    return "Unknown"


async def cleanup_files(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except:
            pass


async def process_thumbnail(thumb_path):
    if not thumb_path or not os.path.exists(thumb_path):
        return None

    try:
        with Image.open(thumb_path) as img:
            img = img.convert("RGB").resize((320, 320))
            img.save(thumb_path, "JPEG")
        return thumb_path
    except:
        await cleanup_files(thumb_path)
        return None


# ================= MAIN HANDLER =================
@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):

    user_id = message.from_user.id
    format_template = await codeflixbots.get_format_template(user_id)

    if not format_template:
        return await message.reply_text("Set format first using /autorename")

    file_id = None
    file_name = None
    media_type = None

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        media_type = "document"

    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video"
        media_type = "video"

    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio"
        media_type = "audio"

    if not file_id:
        return await message.reply_text("Unsupported file")

    if await check_anti_nsfw(file_name, message):
        return await message.reply_text("NSFW detected")

    if file_id in renaming_operations:
        if (datetime.now() - renaming_operations[file_id]).seconds < 10:
            return

    renaming_operations[file_id] = datetime.now()

    # SAFE INIT
    download_path = None
    metadata_path = None
    thumb_path = None

    try:
        season, episode = extract_season_episode(file_name)
        quality = extract_quality(file_name)

        format_template = format_template.replace("{season}", season or "XX")
        format_template = format_template.replace("{episode}", episode or "XX")
        format_template = format_template.replace("{quality}", quality)

        ext = os.path.splitext(file_name)[1] or ".mp4"
        new_filename = f"{format_template}{ext}"

        download_path = f"downloads/{new_filename}"
        metadata_path = f"metadata/{new_filename}"

        os.makedirs("downloads", exist_ok=True)
        os.makedirs("metadata", exist_ok=True)

        msg = await message.reply_text("Downloading...")

        file_path = await client.download_media(
            message,
            file_name=download_path,
            progress=progress_for_pyrogram,
            progress_args=("Downloading...", msg, time.time())
        )

        await msg.edit("Processing...")

        file_path = metadata_path  # placeholder safe pass

        await msg.edit("Preparing upload...")

        caption = await codeflixbots.get_caption(message.chat.id) or new_filename
        thumb = await codeflixbots.get_thumbnail(message.chat.id)

        if thumb:
            thumb_path = await client.download_media(thumb)

        thumb_path = await process_thumbnail(thumb_path)

        await msg.edit("Uploading...")

        upload_params = {
            "chat_id": message.chat.id,
            "caption": caption,
            "thumb": thumb_path,
            "progress": progress_for_pyrogram,
            "progress_args": ("Uploading...", msg, time.time())
        }

        if media_type == "document":
            await client.send_document(document=file_path, **upload_params)

        elif media_type == "video":
            await client.send_video(video=file_path, **upload_params)

        elif media_type == "audio":
            await client.send_audio(audio=file_path, **upload_params)

        await msg.delete()

    except Exception as e:
        logger.error(e)
        await message.reply_text(f"Error: {e}")

    finally:
        await cleanup_files(download_path, metadata_path, thumb_path)
        renaming_operations.pop(file_id, None)