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
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", "0"))
BATCH_SIZE = 2000  # حجم كل دفعة من الرسائل
DELAY_BETWEEN_ALBUMS = int(os.getenv("DELAY_BETWEEN_ALBUMS", "0"))  # تأخير بين إرسال كل ألبوم

# متغير لتخزين آخر قيمة تأخير مستخدمة
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
        sent_messages = await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم يحتوي على الرسائل: {[msg.id for msg in album_messages]}")
        
        # 📌 تثبيت أول رسالة من الألبوم في القناة الوجهة
        first_sent_msg = sent_messages[0]
        await client.pin_chat_message(dest_chat_id, first_sent_msg.id, disable_notification=True)
        print(f"📌 تم تثبيت الرسالة {first_sent_msg.id} في القناة الوجهة.")
    
    except errors.FloodWait as e:
        print(f"⏳ FloodWait: الانتظار {e.value} ثانية...")
        await asyncio.sleep(e.value + 5)
        await send_album(client, dest_chat_id, source_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل إرسال الألبوم: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    try:
        source_chat = await client.join_chat(source_invite)
        print("✅ تم الاتصال بالقناة المصدر")
    except errors.UserAlreadyParticipant:
        source_chat = await client.get_chat(source_invite)
        print("✅ الحساب مشارك مسبقاً في القناة المصدر")
    
    try:
        dest_chat = await client.join_chat(dest_invite)
        print("✅ تم الاتصال بالقناة الوجهة")
    except errors.FloodWait as e:
        print(f"⚠️ FloodWait: الانتظار {e.value} ثانية قبل إعادة المحاولة للقناة الوجهة.")
        await asyncio.sleep(e.value + 5)
        dest_chat = await client.join_chat(dest_invite)
    except errors.UserAlreadyParticipant:
        dest_chat = await client.get_chat(dest_invite)
        print("✅ الحساب مشارك مسبقاً في القناة الوجهة")
    
    print("🔍 جاري جلب جميع الرسائل في النطاق المحدد...")
    all_messages = await fetch_messages_in_range(client, source_chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID)
    print(f"🔍 تم جلب {len(all_messages)} رسالة ضمن النطاق")
    
    for batch in chunk_messages(all_messages, BATCH_SIZE):
        albums = group_albums(batch)
        sorted_albums = sorted(albums.items(), key=lambda item: min(m.id for m in item[1]))
        for album_id, msgs in sorted_albums:
            delay = get_random_delay()
            print(f"⏳ سيتم الانتظار {delay} ثانية قبل إرسال هذا الألبوم")
            await asyncio.sleep(delay)
            print(f"📂 ألبوم {album_id} يحتوي على الرسائل: {[m.id for m in msgs]}")
            await send_album(client, dest_chat.id, source_chat.id, msgs)
        print(f"⚡ تم معالجة دفعة من {len(batch)} رسالة")
    
    print("✅ الانتهاء من نقل جميع الألبومات!")

async def main():
    async with Client(
        name="media_transfer_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        print("🚀 بدء تشغيل البوت...")
        await process_channel(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 جاري تهيئة النظام...")
    asyncio.run(main())
