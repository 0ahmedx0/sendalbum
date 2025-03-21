import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل الإعدادات من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
# بدلاً من SESSION، سنستخدم توكن البوت
BOT_TOKEN = os.getenv("BOT_TOKEN")
SOURCE_INVITE = os.getenv("CHANNEL_ID")        # رابط أو معرف القناة المصدر (القناة الخاصة)
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")        # رابط أو معرف القناة الوجهة (يجب أن يكون البوت مشرفاً فيها)
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", ""))
BATCH_SIZE = 1000  # حجم كل دفعة من الرسائل
DELAY_BETWEEN_ALBUMS = 30  # تأخير بين إرسال كل ألبوم

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
        first_msg_id = album_messages[0].id
        src = str(source_chat_id)
        if src.startswith("-100"):
            channel_part = src[4:]
        else:
            channel_part = src
        link = f"https://t.me/c/{channel_part}/{first_msg_id}"
        await client.send_message(dest_chat_id, f"📌 رابط الرسالة: {link}")
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
            print(f"📂 ألبوم {album_id} يحتوي على الرسائل: {[m.id for m in msgs]}")
            await send_album(client, dest_chat.id, source_chat.id, msgs)
            await asyncio.sleep(DELAY_BETWEEN_ALBUMS)
        print(f"⚡ تم معالجة دفعة من {len(batch)} رسالة")
    
    print("✅ الانتهاء من نقل جميع الألبومات!")

async def main():
    async with Client(
        name="media_transfer_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN  # استخدام توكن البوت بدلاً من session_string
    ) as client:
        print("🚀 بدء تشغيل البوت...")
        await process_channel(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 جاري تهيئة النظام...")
    asyncio.run(main())
