import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

load_dotenv()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
BATCH_SIZE = 100
DELAY_BETWEEN_ALBUMS = 10

async def collect_albums_batch(client: Client, chat_id: int, offset_id: int):
    albums = {}
    messages = []
    
    effective_offset = offset_id if offset_id is not None else 0
    
    async for message in client.get_chat_history(
        chat_id,
        limit=BATCH_SIZE,
        offset_id=effective_offset
    ):
        messages.append(message)
        if len(messages) >= BATCH_SIZE:
            break
    
    if not messages:
        return None, None
    
    messages.reverse()
    
    for message in messages:
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    
    next_offset = messages[-1].id - 1
    
    return albums, next_offset

async def send_album(client: Client, dest_chat_id: int, messages: list):
    try:
        sorted_messages = sorted(messages, key=lambda m: m.id)
        media_group = []
        
        for idx, msg in enumerate(sorted_messages):
            if msg.photo:
                media = InputMediaPhoto(msg.photo.file_id)
            elif msg.video:
                media = InputMediaVideo(msg.video.file_id, supports_streaming=True)
            elif msg.document:
                if msg.document.mime_type.startswith('video/'):
                    media = InputMediaVideo(msg.document.file_id, supports_streaming=True)
                else:
                    media = InputMediaDocument(msg.document.file_id)
            else:
                continue
            
            if idx == 0 and msg.caption:
                media.caption = msg.caption
            
            media_group.append(media)
        
        await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم ({len(messages)} رسائل) - الأرقام: {[m.id for m in sorted_messages]}")
        await asyncio.sleep(DELAY_BETWEEN_ALBUMS)
        
    except errors.FloodWait as e:
        print(f"⏳ تم إيقاف البوت لمدة {e.value} ثانية")
        await asyncio.sleep(e.value + 1)
        await send_album(client, dest_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل الإرسال: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    try:
        source_chat = await client.join_chat(source_invite)
    except errors.UserAlreadyParticipant:
        source_chat = await client.get_chat(source_invite)
    
    try:
        dest_chat = await client.join_chat(dest_invite)
    except errors.UserAlreadyParticipant:
        dest_chat = await client.get_chat(dest_invite)
    
    current_offset = None
    total_albums = 0
    
    while True:
        albums, next_offset = await collect_albums_batch(client, source_chat.id, current_offset)
        
        if not albums:
            break
        
        sorted_albums = sorted(albums.items(), key=lambda x: min(m.id for m in x[1]))
        
        for album_id, messages in sorted_albums:
            await send_album(client, dest_chat.id, messages)
            total_albums += 1
        
        current_offset = next_offset
    
    print(f"✅ تم نقل {total_albums} ألبوم بنجاح")

async def main():
    async with Client(
        "media_transfer_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        await process_channel(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    asyncio.run(main())
