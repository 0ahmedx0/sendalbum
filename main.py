import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل الإعدادات من ملف البيئة
load_dotenv()

# تهيئة المتغيرات
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
BATCH_SIZE = 100  # حجم كل دفعة من الرسائل
DELAY_BETWEEN_ALBUMS = 10  # تأخير بين إرسال كل ألبوم
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", "14356"))  # حدد آخر رسالة تريد معالجتها

async def collect_albums_batch(client: Client, chat_id: int, current_id: int, last_msg_id: int):
    """
    يجمع دفعة من الرسائل بدءًا من current_id حتى يصل العدد إلى BATCH_SIZE 
    أو ينتهي المجال حتى LAST_MESSAGE_ID، ويجمع الرسائل التي تحتوي على media_group_id في ألبومات.
    """
    albums = {}
    messages = []
    
    async for message in client.get_chat_history(
        chat_id,
        limit=BATCH_SIZE,
        min_id=current_id - 1,   # يجلب الرسائل التي يكون id أكبر من current_id - 1
        max_id=last_msg_id        # لا يتجاوز LAST_MESSAGE_ID
    ):
        if message.id < current_id:
            continue
        messages.append(message)
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    
    if not messages:
        return None, None
    
    # عكس ترتيب الرسائل للحصول على الترتيب التصاعدي (من الأقدم إلى الأحدث)
    messages.reverse()
    
    # تحديث نقطة البداية للدفعة التالية: نستخدم معرف آخر رسالة من الدفعة دون إضافة 1
    next_current_id = messages[-1].id
    return albums, next_current_id

async def send_album(client: Client, dest_chat_id: int, messages: list):
    """
    يقوم بتجهيز وإرسال ألبوم من الرسائل مع التعامل مع أخطاء FloodWait.
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
            
            # إضافة التسمية التوضيحية للعنصر الأول إن وُجدت
            if idx == 0 and msg.caption:
                media.caption = msg.caption
            media_group.append(media)
        
        await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم ({len(sorted_messages)} رسائل) - الأرقام: {[m.id for m in sorted_messages]}")
    except errors.FloodWait as e:
        print(f"⏳ تم إيقاف البوت لمدة {e.value} ثانية بسبب FloodWait")
        await asyncio.sleep(e.value + 1)
        await send_album(client, dest_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل إرسال الألبوم: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    """
    ينضم إلى القناتين، ويجمع الرسائل على دفعات من 1000، ثم يجمع الألبومات ويرسلها،
    ويستكمل العملية بدءًا من آخر رسالة من الدفعة السابقة.
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
    
    current_id = FIRST_MSG_ID
    total_albums = 0
    
    while True:
        albums, next_current_id = await collect_albums_batch(client, source_chat.id, current_id, LAST_MESSAGE_ID)
        if not albums:
            print("🎉 تم معالجة جميع الرسائل!")
            break
        
        sorted_albums = sorted(albums.items(), key=lambda x: min(m.id for m in x[1]))
        for album_id, messages in sorted_albums:
            print(f"📂 ألبوم {album_id} يحتوي على الرسائل: {[m.id for m in messages]}")
            await send_album(client, dest_chat.id, messages)
            total_albums += 1
            await asyncio.sleep(DELAY_BETWEEN_ALBUMS)
        
        print(f"⚡ تم معالجة دفعة من الرسائل من {current_id} إلى {next_current_id}")
        current_id = next_current_id  # بدء الدفعة التالية من آخر رسالة تمت معالجتها
    
    print(f"✅ الانتهاء من نقل {total_albums} ألبوم بنجاح")

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
