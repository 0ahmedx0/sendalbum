import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل الإعدادات من ملف البيئة
load_dotenv()

# تهيئة المتغيرات
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", "14356"))
BATCH_SIZE = 1000  # حجم كل دفعة من الرسائل
DELAY_BETWEEN_ALBUMS = 10 # تأخير بين إرسال كل ألبوم

async def fetch_messages_in_range(client: Client, chat_id: int, first_id: int, last_id: int):
    """
    يجلب جميع الرسائل من القناة التي يكون رقمها بين first_id و last_id.
    نظرًا لعدم دعم الترتيب التصاعدي مباشرةً، نقوم بجلب الرسائل باستخدام get_chat_history 
    (التي تُرجع الرسائل بترتيب تنازلي)، ثم نقوم بفلترتها وترتيبها تصاعديًا.
    """
    messages = []
    # نستخدم offset_id = last_id + 1 للحصول على الرسائل التي تكون id < (last_id + 1) أي <= last_id
    offset_id = last_id + 1
    while True:
        batch = []
        async for message in client.get_chat_history(chat_id, offset_id=offset_id, limit=1000):
            # نتأكد من عدم تجاوز النطاق
            if message.id < first_id:
                break
            batch.append(message)
        if not batch:
            break
        messages.extend(batch)
        offset_id = batch[-1].id  # تحديث نقطة البداية للدفعة التالية
        # إذا كانت آخر رسالة في الدفعة أقدم من first_id، ننهي العملية
        if batch[-1].id < first_id:
            break
    # فلترة الرسائل التي تقع ضمن النطاق وترتيبها تصاعديًا
    messages = [m for m in messages if m.id >= first_id]
    messages.sort(key=lambda m: m.id)
    return messages

def chunk_messages(messages, chunk_size):
    """يقسم القائمة إلى دفعات (chunks) من الحجم المحدد."""
    for i in range(0, len(messages), chunk_size):
        yield messages[i:i+chunk_size]

def group_albums(messages):
    """
    يجمع الرسائل التي تحمل media_group_id في قاموس،
    حيث يكون المفتاح هو media_group_id والقيمة قائمة الرسائل.
    """
    albums = {}
    for msg in messages:
        if msg.media_group_id:
            albums.setdefault(msg.media_group_id, []).append(msg)
    return albums

async def send_album(client: Client, dest_chat_id: int, messages: list):
    """
    يُجهز الرسائل ضمن الألبوم (حسب نوع الوسائط) ويرسلها باستخدام send_media_group.
    كما يتعامل مع أخطاء FloodWait.
    """
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
            # إضافة التسمية التوضيحية للعنصر الأول فقط إن وُجدت
            if idx == 0 and msg.caption:
                media.caption = msg.caption
            media_group.append(media)
        await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم يحتوي على الرسائل: {[m.id for m in sorted_messages]}")
    except errors.FloodWait as e:
        print(f"⏳ FloodWait: الانتظار {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        await send_album(client, dest_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل إرسال الألبوم: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    """
    ينضم إلى القناتين، ثم يجلب جميع الرسائل ضمن النطاق المطلوب،
    ويقسمها إلى دفعات من 1000 رسالة، ثم يجمع الألبومات في كل دفعة ويرسلها.
    """
    # الانضمام للقناة المصدر
    try:
        source_chat = await client.join_chat(source_invite)
        print("✅ تم الاتصال بالقناة المصدر")
    except errors.UserAlreadyParticipant:
        source_chat = await client.get_chat(source_invite)
        print("✅ الحساب مشارك مسبقاً في القناة المصدر")
    # الانضمام للقناة الوجهة
    try:
        dest_chat = await client.join_chat(dest_invite)
        print("✅ تم الاتصال بالقناة الوجهة")
    except errors.UserAlreadyParticipant:
        dest_chat = await client.get_chat(dest_invite)
        print("✅ الحساب مشارك مسبقاً في القناة الوجهة")
    
    print("🔍 جاري جلب جميع الرسائل في النطاق المحدد...")
    all_messages = await fetch_messages_in_range(client, source_chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID)
    print(f"🔍 تم جلب {len(all_messages)} رسالة ضمن النطاق")
    
    # تقسيم الرسائل إلى دفعات من 1000 رسالة
    for batch in chunk_messages(all_messages, BATCH_SIZE):
        # تجميع الألبومات داخل الدفعة الحالية
        albums = group_albums(batch)
        # ترتيب الألبومات حسب أقدم رسالة فيها
        sorted_albums = sorted(albums.items(), key=lambda x: min(m.id for m in x[1]))
        for album_id, msgs in sorted_albums:
            print(f"📂 ألبوم {album_id} يحتوي على الرسائل: {[m.id for m in msgs]}")
            await send_album(client, dest_chat.id, msgs)
            await asyncio.sleep(DELAY_BETWEEN_ALBUMS)
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
