import os
import time
import re
import asyncio
from pyrogram import Client, filters

# ----------------------------
# Helpers
# ----------------------------

def clean_filename(name: str) -> str:
    # remove illegal characters
    return re.sub(r'[\\/*?:"<>|]', "", name)

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)

# ----------------------------
# Rename Handler
# ----------------------------

@Client.on_message(filters.command("rename"))
async def rename_file(client, message):

    if not message.reply_to_message:
        return await message.reply_text("Reply to a file to rename it.")

    doc = message.reply_to_message

    if not (doc.document or doc.video or doc.audio):
        return await message.reply_text("Only file/video/audio supported.")

    new_name = " ".join(message.command[1:])

    if not new_name:
        return await message.reply_text("Give a new filename.")

    new_name = clean_filename(new_name)

    msg = await message.reply_text("Downloading...")

    # ----------------------------
    # DOWNLOAD FILE
    # ----------------------------
    file_path = await client.download_media(doc)

    if not file_path or not os.path.exists(file_path):
        return await msg.edit("Download failed.")

    await msg.edit("Renaming...")

    # ----------------------------
    # SET NEW PATH
    # ----------------------------
    ext = os.path.splitext(file_path)[-1]
    base_dir = "metadata"
    ensure_dir(base_dir)

    new_path = os.path.abspath(os.path.join(base_dir, new_name + ext))

    # rename locally
    try:
        os.rename(file_path, new_path)
    except Exception as e:
        return await msg.edit(f"Rename failed: {e}")

    if not os.path.exists(new_path):
        return await msg.edit("File missing after rename.")

    await msg.edit("Uploading...")

    # ----------------------------
    # UPLOAD BACK
    # ----------------------------
    try:
        await client.send_document(
            chat_id=message.chat.id,
            document=new_path,
            file_name=new_name + ext,
            caption=f"Renamed by bot\n\n📁 {new_name + ext}"
        )
    except Exception as e:
        return await msg.edit(f"Upload failed: {e}")

    await msg.delete()

    # ----------------------------
    # CLEANUP
    # ----------------------------
    try:
        os.remove(new_path)
    except:
        pass