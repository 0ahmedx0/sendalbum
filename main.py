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
BATCH_SIZE = 1000  # حجم كل دفعة من الرسائل
DELAY_BETWEEN_ALBUMS = 2  # تأخير بين إرسال كل ألبوم

async def collect_albums_batch(client: Client, chat_id: int, offset_id: int):
    """
    تجميع الألبومات في دفعات من الأقدم إلى الأحدث
    """
    albums = {}
    messages = []
    
    # جلب الرسائل من الأحدث إلى الأقدم
    async for message in client.get_chat_history(
        chat_id,
        limit=BATCH_SIZE,
        offset_id=offset_id
    ):
        messages.append(message)
        if len(messages) >= BATCH_SIZE:
            break
    
    # إذا لم يتم العثور على رسائل جديدة
    if not messages:
        return None, None
    
    # عكس الترتيب للعمل من الأقدم إلى الأحدث
    messages.reverse()
    
    # تجميع الألبومات
    for message in messages:
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    
    # تحديث الـ offset للدفعة التالية
    next_offset = messages[-1].id - 1
    
    return albums, next_offset

async def send_album(client: Client, dest_chat_id: int, messages: list):
    """
    إرسال ألبوم واحد مع التحكم في الأخطاء
    """
    try:
        # ترتيب الرسائل وتجهيز الوسائط
        sorted_messages = sorted(messages, key=lambda m: m.id)
        media_group = []
        
        for idx, msg in enumerate(sorted_messages):
            # تحديد نوع الوسائط
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
            
            # إضافة التسمية التوضيحية للعنصر الأول فقط
            if idx == 0 and msg.caption:
                media.caption = msg.caption
            
            media_group.append(media)
        
        # إرسال الألبوم
        await client.send_media_group(dest_chat_id, media_group)
        print(f"✅ تم إرسال ألبوم ({len(messages)} رسائل) - الأرقام: {[m.id for m in sorted_messages]}")
        
    except errors.FloodWait as e:
        print(f"⏳ تم إيقاف البوت لمدة {e.value} ثانية بسبب FloodWait")
        await asyncio.sleep(e.value + 1)
        await send_album(client, dest_chat_id, messages)
    except Exception as e:
        print(f"⚠️ فشل إرسال الألبوم: {str(e)}")

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    """
    المعالجة الرئيسية للقنوات
    """
    # الانضمام للقنوات
    try:
        source_chat = await client.join_chat(source_invite)
        print("✅ تم الاتصال بالقناة المصدر")
    except errors.UserAlreadyParticipant:
        source_chat = await client.get_chat(source_invite)
        print("✅ الحساب مشارك مسبقاً في القناة المصدر")
    
    try:
        dest_chat = await client.join_chat(dest_invite)
        print("✅ تم الاتصال بالقناة الوجهة")
    except errors.UserAlreadyParticipant:
        dest_chat = await client.get_chat(dest_invite)
        print("✅ الحساب مشارك مسبقاً في القناة الوجهة")
    
    # بدء المعالجة بالدفعات
    current_offset = None
    total_albums = 0
    
    while True:
        # جلب الدفعة الحالية
        albums, next_offset = await collect_albums_batch(client, source_chat.id, current_offset)
        
        if not albums:
            print("🎉 تم معالجة جميع الرسائل!")
            break
        
        # معالجة الألبومات بالترتيب
        sorted_albums = sorted(albums.items(), key=lambda x: min(m.id for m in x[1]))
        
        for album_id, messages in sorted_albums:
            await send_album(client, dest_chat.id, messages)
            total_albums += 1
            await asyncio.sleep(DELAY_BETWEEN_ALBUMS)
        
        print(f"⚡ تم معالجة {len(albums)} ألبوم في هذه الدفعة")
        current_offset = next_offset
    
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
