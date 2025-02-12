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
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", 1))
BATCH_SIZE = 1000
DELAY_BETWEEN_ALBUMS = 2

async def collect_albums_batch(client: Client, chat_id: int, offset_id: int):
    """
    تجميع الدفعات باستخدام offset_id
    """
    albums = {}
    messages = []
    
    async for message in client.get_chat_history(
        chat_id,
        limit=BATCH_SIZE,
        offset_id=offset_id
    ):
        if message.id < FIRST_MSG_ID:
            break  # التوقف عند الوصول إلى FIRST_MSG_ID
        
        messages.append(message)
        if len(messages) >= BATCH_SIZE:
            break
    
    if not messages:
        return None, None
    
    # ترتيب الرسائل من الأقدم إلى الأحدث
    messages.reverse()
    
    # تجميع الألبومات
    for message in messages:
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    
    # تحديث الـ offset للدفعة التالية
    next_offset = messages[-1].id - 1 if messages else offset_id
    
    return albums, next_offset

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    # ... (نفس الكود السابق للانضمام للقنوات)
    
    current_offset = None  # البدء من أحدث رسالة
    total_albums = 0
    
    while True:
        albums, next_offset = await collect_albums_batch(client, source_chat.id, current_offset)
        
        if not albums:
            break
        
        # ترتيب الألبومات داخل الدفعة
        sorted_albums = sorted(
            albums.items(),
            key=lambda x: min(m.id for m in x[1])
        )
        
        # معالجة كل ألبوم
        for album_id, messages in sorted_albums:
            await send_album(client, dest_chat.id, messages)
            total_albums += 1
        
        current_offset = next_offset
    
    print(f"✅ تم نقل {total_albums} ألبوم")

# ... (بقية الدوال كما هي دون تغيير)
