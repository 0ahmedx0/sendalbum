import asyncio
import os
import random
from dotenv import load_dotenv
from pyrogram import Client, errors

# تحميل الإعدادات من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", ""))

def get_random_delay():
    """اختيار تأخير عشوائي من بين 5، 10 أو 15 ثانية"""
    return random.choice([5, 10, 15])

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

async def send_document_link(client: Client, dest_chat_id: int, source_chat_id: int, message):
    """
    يقوم ببناء رابط الرسالة وإرساله إلى القناة الوجهة.
    """
    try:
        msg_id = message.id
        src = str(source_chat_id)
        if src.startswith("-100"):
            channel_part = src[4:]
        else:
            channel_part = src
        link = f"https://t.me/c/{channel_part}/{msg_id}"
        await client.send_message(dest_chat_id, f"📌 رابط الرسالة الأصلية: {link}")
        print(f"✅ تم إرسال رابط الرسالة: {link}")
    except errors.FloodWait as e:
        print(f"⏳ FloodWait: الانتظار {e.value} ثانية لإرسال الرابط")
        await asyncio.sleep(e.value + 5)
        await send_document_link(client, dest_chat_id, source_chat_id, message)
    except Exception as e:
        print(f"⚠️ فشل إرسال الرابط: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    """
    ينضم إلى القناتين، يجلب الرسائل ضمن النطاق المحدد،
    يصفي الرسائل التي تحتوي على مستندات فقط،
    ثم لكل رسالة مستند يقوم بإرسال رابط الرسالة مع تأخير عشوائي (5، 10 أو 15 ثانية).
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
    
    # تصفية الرسائل التي تحتوي على مستندات فقط
    doc_messages = [m for m in all_messages if m.document]
    print(f"🔍 تم العثور على {len(doc_messages)} رسالة تحتوي على مستندات")
    
    for msg in doc_messages:
        delay = get_random_delay()
        print(f"⏳ سيتم الانتظار {delay} ثانية قبل إرسال رابط الرسالة التي تحمل المستند (ID: {msg.id})")
        await asyncio.sleep(delay)
        await send_document_link(client, dest_chat.id, source_chat.id, msg)
        
    print("✅ الانتهاء من إرسال روابط جميع المستندات!")

async def main():
    async with Client(
        name="document_link_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        print("🚀 بدء تشغيل البوت...")
        await process_channel(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 جاري تهيئة النظام...")
    asyncio.run(main())
