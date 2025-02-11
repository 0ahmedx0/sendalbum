import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل إعدادات البيئة من ملف .env
load_dotenv()

# إعدادات Pyrogram
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")  # يجب أن تكون هذه السلسلة الجلسة (session string)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))         # القناة المصدر
CHANNEL_ID_LOG = int(os.getenv("CHANNEL_ID_LOG", "0"))   # القناة الوجهة التي سيتم تحويل الرسائل إليها
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "0"))       # معرف أول رسالة للبدء

async def iter_history(client, chat_id, min_id, limit=100):
    """
    مولّد غير متزامن لاستعراض تاريخ الرسائل باستخدام الترقيم (pagination).
    يستخدم الدالة get_chat_history لجلب الرسائل التي يكون معرفها أكبر من min_id.
    """
    offset_id = 0
    while True:
        messages = await client.get_chat_history(chat_id, offset_id=offset_id, min_id=min_id, limit=limit)
        if not messages:
            break
        for message in messages:
            yield message
        offset_id = messages[-1].message_id

async def collect_albums(client, chat_id, first_msg_id):
    """
    يجمع جميع الرسائل التي تنتمي إلى ألبومات (بوجود الخاصية media_group_id)
    ويعيد قاموسًا بالشكل: { media_group_id: [رسائل الألبوم] }
    """
    albums = {}
    async for message in iter_history(client, chat_id, first_msg_id):
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    return albums

async def transfer_album(client, source_chat, destination_chat, album_messages):
    """
    يقوم بتحويل ألبوم من الرسائل باستخدام دالة send_media_group الخاصة بـ Pyrogram.
    يتم تجميع وسائط الرسائل وإرسالها كمجموعة دون تنزيل الملفات محلياً.
    """
    # ترتيب الرسائل تصاعدياً بناءً على معرف الرسالة للحفاظ على الترتيب الأصلي
    album_messages_sorted = sorted(album_messages, key=lambda m: m.message_id)
    
    media_group = []
    for index, message in enumerate(album_messages_sorted):
        input_media = None
        # تضمين التسمية التوضيحية فقط للرسالة الأولى
        caption = message.caption if index == 0 and message.caption else ""
        if message.photo:
            input_media = InputMediaPhoto(media=message.photo.file_id, caption=caption)
        elif message.video:
            input_media = InputMediaVideo(media=message.video.file_id, caption=caption)
        elif message.document:
            input_media = InputMediaDocument(media=message.document.file_id, caption=caption)
        else:
            print(f"⚠️ الرسالة {message.message_id} لا تحتوي على وسائط قابلة للإرسال ضمن المجموعة.")
            continue
        
        media_group.append(input_media)
    
    if not media_group:
        print("⚠️ لا توجد وسائط لإرسالها في هذا الألبوم، يتم تخطيه...")
        return
    
    try:
        await client.send_media_group(chat_id=destination_chat, media=media_group)
        print(f"✅ تم إرسال ألبوم الرسائل {[msg.message_id for msg in album_messages_sorted]} إلى القناة الوجهة")
    except errors.FloodWait as e:
        print(f"⏳ تجاوز الحد: الانتظار {e.x} ثانية...")
        await asyncio.sleep(e.x + 1)
        try:
            await client.send_media_group(chat_id=destination_chat, media=media_group)
        except Exception as e:
            print(f"⚠️ خطأ في إعادة إرسال الألبوم: {e}")
    except Exception as e:
        print(f"⚠️ خطأ في إرسال ألبوم الرسائل {[msg.message_id for msg in album_messages_sorted]}: {e}")

async def process_albums(client, channel_id):
    """
    يجمع ألبومات الرسائل من القناة المصدر، ثم ينقل كل ألبوم باستخدام الدالة transfer_album.
    """
    print("🔍 جاري تجميع الألبومات...")
    albums = await collect_albums(client, channel_id, FIRST_MSG_ID)
    print(f"تم العثور على {len(albums)} ألبوم.")
    
    tasks = []
    for media_group_id, messages in albums.items():
        if len(messages) > 1:  # نعتبر الرسائل ألبومًا إذا كان يحتوي على أكثر من رسالة
            print(f"📂 ألبوم {media_group_id} يحتوي على الرسائل: {[msg.message_id for msg in messages]}")
            tasks.append(transfer_album(client, channel_id, CHANNEL_ID_LOG, messages))
    
    if tasks:
        await asyncio.gather(*tasks)
    else:
        print("لم يتم العثور على ألبومات.")

async def main():
    # إنشاء عميل Pyrogram باستخدام السلسلة الجلسة (session string)
    async with Client(
        "my_session",  # يمكن استخدام أي اسم للجلسة
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        print("🚀 العميل متصل بنجاح.")
        await process_albums(client, CHANNEL_ID)

if __name__ == "__main__":
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
