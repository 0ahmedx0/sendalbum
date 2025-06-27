import asyncio
import os
import random
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل الإعدادات من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SOURCE_ID = int(os.getenv("CHANNEL_ID"))         # ← chat_id للقناة الخاصة
DEST_ID = int(os.getenv("CHANNEL_ID_LOG"))       # ← chat_id للقناة الوجهة
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", ""))
BATCH_SIZE = 1000

# متغير لتخزين آخر قيمة تأخير عشوائي
prev_delay = None

def get_random_delay(min_delay=5, max_delay=40, min_diff=10):
    global prev_delay
    delay = random.randint(min_delay, max_delay)
    while prev_delay is not None and abs(delay - prev_delay) < min_diff:
        delay = random.randint(min_delay, max_delay)
    prev_delay = delay
    return delay

async def fetch_messages_in_range(client: Client, chat_id: int, first_id: int, last_id: int):
    messages = []
    offset_id = last_id + 1
    while True:
        batch = []
        async for message in client.get_chat_history(chat_id, offset_id=offset_id, limit=1000):
            if message.id < first_id:
                break
            batch.append(message)
        if not batch:
            break
        messages.extend(batch)
        offset_id = batch[-1].id
        if batch[-1].id < first_id:
            break
    messages = [m for m in messages if m.id >= first_id]
    messages.sort(key=lambda m: m.id)
    return messages

def chunk_messages(messages, chunk_size):
    for i in range(0, len(messages), chunk_size):
        yield messages[i:i+chunk_size]

def group_albums(messages):
    albums = {}
    for msg in messages:
        if msg.media_group_id:
            albums.setdefault(msg.media_group_id, []).append(msg)
    return albums

async def send_album(client: Client, dest_chat_id: int, source_chat_id: int, messages: list):
    album_messages = messages  
    media_group = []
    for idx, msg in enumerate(album_messages):
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
    try:
        await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم يحتوي على الرسائل: {[msg.id for msg in album_messages]}")
    except errors.FloodWait as e:
        print(f"⏳ FloodWait: الانتظار {e.value} ثانية...")
        await asyncio.sleep(e.value + 5)
        await send_album(client, dest_chat_id, source_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل إرسال الألبوم: {str(e)}")

async def process_channel(client: Client, source_id: int, dest_id: int):
    try:
        source_chat = await client.get_chat(source_id)
        print("✅ تم الاتصال بالقناة المصدر")
    except Exception as e:
        print(f"❌ فشل الاتصال بالقناة المصدر: {e}")
        return

    try:
        dest_chat = await client.get_chat(dest_id)
        print("✅ تم الاتصال بالقناة الوجهة")
    except Exception as e:
        print(f"❌ فشل الاتصال بالقناة الوجهة: {e}")
        return

    print("🔍 جاري جلب جميع الرسائل في النطاق المحدد...")
    all_messages = await fetch_messages_in_range(client, source_chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID)
    print(f"🔍 تم جلب {len(all_messages)} رسالة ضمن النطاق")

    for batch in chunk_messages(all_messages, BATCH_SIZE):
        albums = group_albums(batch)
