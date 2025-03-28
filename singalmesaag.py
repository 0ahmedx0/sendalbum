import asyncio
import os
import random
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo

# تحميل الإعدادات من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", ""))
TARGET_MESSAGES_COUNT = 2000   # عدد الرسائل التي سيتم تجميعها لتحويلها إلى ألبوم
ALBUM_CHUNK_SIZE = 10          # الحد الأقصى لكل ألبوم (Telegram يسمح بحد أقصى 10 وسائط)
DELAY_MIN = 30  
DELAY_MAX = 90  
MIN_DIFF = 30

prev_delay = None

def get_random_delay(min_delay=DELAY_MIN, max_delay=DELAY_MAX, min_diff=MIN_DIFF):
    """
    توليد تأخير عشوائي مع التأكد من عدم تشابهه مع القيمة السابقة بفارق بسيط.
    """
    global prev_delay
    delay = random.randint(min_delay, max_delay)
    while prev_delay is not None and abs(delay - prev_delay) < min_diff:
        delay = random.randint(min_delay, max_delay)
    prev_delay = delay
    return delay

async def fetch_messages_in_range(client: Client, chat_id: int, first_id: int, last_id: int):
    """
    يجلب جميع الرسائل من القناة ضمن النطاق المحدد.
    """
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
    """يقسم القائمة إلى دفعات (chunks) بالحجم المحدد."""
    for i in range(0, len(messages), chunk_size):
        yield messages[i:i+chunk_size]

async def send_album(client: Client, dest_chat_id: int, source_chat_id: int, messages: list):
    """
    يقوم بتحويل قائمة من الرسائل إلى ألبوم باستخدام send_media_group.
    يتم إرسال الألبوم أولاً ثم بعد تأخير قصير يتم إرسال رابط الرسالة الأولى من القناة المصدر.
    """
    media_group = []
    for idx, msg in enumerate(messages):
        media = None
        if msg.photo:
            media = InputMediaPhoto(msg.photo.file_id)
        elif msg.video:
            media = InputMediaVideo(msg.video.file_id, supports_streaming=True)
        elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/"):
            # تحويل المستند إلى فيديو قابل للبث
            media = InputMediaVideo(msg.document.file_id, supports_streaming=True)

        if not media:
            continue  # تخطي الرسائل غير المدعومة

        if idx == 0 and msg.caption:
            media.caption = msg.caption

        media_group.append(media)

    if not media_group:
        print("⚠️ لا يوجد وسائط مناسبة لإرسال الألبوم.")
        return

    try:
        # إرسال الألبوم أولاً
        await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم يحتوي على الرسائل: {[msg.id for msg in messages]}")
        # تأخير بسيط للتأكد من وصول الألبوم قبل إرسال الرابط
        await asyncio.sleep(2)
        # بناء رابط الرسالة الأولى من القناة الأصلية
        first_msg_id = messages[0].id
        src = str(source_chat_id)
        if src.startswith("-100"):
            channel_part = src[4:]
        else:
            channel_part = src
        link = f"https://t.me/c/{channel_part}/{first_msg_id}"
        await client.send_message(dest_chat_id, f"📌 رابط الرسالة الأصلية: {link}")
    except errors.FloodWait as e:
        print(f"⏳ FloodWait: الانتظار {e.value} ثانية لإرسال الألبوم")
        await asyncio.sleep(e.value + 5)
        await send_album(client, dest_chat_id, source_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل إرسال الألبوم: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    """
    ينضم إلى القناتين، يجلب الرسائل ضمن النطاق المحدد،
    يصفي الرسائل غير الموجودة ضمن ألبومات والتي تحتوي على وسائط (يستبعد المستندات الآن)،
    يأخذ أول TARGET_MESSAGES_COUNT رسالة، يقسمها إلى دفعات (كل دفعة تصل إلى 10 رسائل)
    ويقوم بإرسال كل دفعة كألبوم متبوعاً برابط الرسالة الأولى الأصلية.
    """
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
    
    # تصفية الرسائل التي ليست ضمن ألبوم وتحتوي على وسائط (صور أو فيديو) مع استبعاد المستندات
    non_album_messages = [m for m in all_messages if not m.media_group_id and (m.photo or m.video)]
    print(f"🔍 تم العثور على {len(non_album_messages)} رسالة غير ضمن ألبوم تحتوي على وسائط (مستبعدة المستندات)")
    
    # أخذ أول TARGET_MESSAGES_COUNT رسالة فقط
    selected_messages = non_album_messages[:TARGET_MESSAGES_COUNT]
    print(f"🔍 سيتم تحويل {len(selected_messages)} رسالة إلى ألبومات")
    
    # تقسيم الرسائل إلى دفعات بحيث لا يتجاوز كل ألبوم 10 رسائل
    albums = list(chunk_messages(selected_messages, ALBUM_CHUNK_SIZE))
    print(f"🔍 سيتم إرسال {len(albums)} ألبوم(ات)")
    
    for i, album in enumerate(albums, start=1):
        delay = get_random_delay()
        print(f"ألبوم رقم {i}: ⏳ سيتم الانتظار {delay} ثانية قبل إرسال ألبوم يحتوي على الرسائل \n {[m.id for m in album]}")
        await asyncio.sleep(delay)
        await send_album(client, dest_chat.id, source_chat.id, album)
        
    print("✅ الانتهاء من إرسال جميع الألبومات!")

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
