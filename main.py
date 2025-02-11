import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل إعدادات البيئة من ملف .env
load_dotenv()

def convert_channel_id(channel_id_str):
    """
    إذا كان المعرف يبدأ بـ "-100" يتم إزالة هذه البادئة.
    ملاحظة: في Pyrogram يُفضّل استخدام معرف القناة كما هو (سواء كان سالباً أم موجباً)
    أو استخدام اسم القناة (username).
    """
    s = str(channel_id_str)
    # يمكنك تعديل هذه الدالة حسب نوع المدخلات لديك؛ في هذا المثال سنقوم بإرجاع السلسلة كما هي
    return channel_id_str

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")  # يجب أن تكون هذه السلسلة الجلسة (session string)
# استخدم المعرف كما هو أو يمكنك استخدام اسم القناة إذا كانت القناة عامة
CHANNEL_ID = convert_channel_id(os.getenv("CHANNEL_ID", "0"))         # القناة المصدر
CHANNEL_ID_LOG = convert_channel_id(os.getenv("CHANNEL_ID_LOG", "0"))   # القناة الوجهة
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "0"))       # معرف أول رسالة للبدء

async def collect_albums(client: Client, chat_id, first_msg_id: int):
    """
    يجمع الرسائل التي تنتمي إلى ألبومات (تحتوي على media_group_id)
    من تاريخ الدردشة باستخدام get_chat_history مع offset_id = FIRST_MSG_ID - 1.
    يتم التوقف عن القراءة بمجرد الوصول إلى رسالة رقمها أقل من FIRST_MSG_ID.
    """
    albums = {}
    async for message in client.get_chat_history(chat_id, offset_id=first_msg_id - 1):
        if message.message_id < first_msg_id:
            break
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    return albums

async def transfer_album(client: Client, source_chat, destination_chat, album_messages: list):
    """
    ينقل ألبوم من الرسائل باستخدام send_media_group في Pyrogram.
    يقوم بترتيب الرسائل تصاعدياً وتجميع الوسائط لإرسالها كمجموعة.
    """
    album_messages_sorted = sorted(album_messages, key=lambda m: m.message_id)
    media_group = []
    for index, message in enumerate(album_messages_sorted):
        caption = message.caption if index == 0 and message.caption else ""
        if message.photo:
            media_group.append(InputMediaPhoto(media=message.photo.file_id, caption=caption))
        elif message.video:
            media_group.append(InputMediaVideo(media=message.video.file_id, caption=caption))
        elif message.document:
            media_group.append(InputMediaDocument(media=message.document.file_id, caption=caption))
        else:
            print(f"⚠️ الرسالة {message.message_id} لا تحتوي على وسائط قابلة للإرسال ضمن المجموعة.")
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
        except Exception as ex:
            print(f"⚠️ خطأ في إعادة إرسال الألبوم: {ex}")
    except Exception as ex:
        print(f"⚠️ خطأ في إرسال ألبوم الرسائل {[msg.message_id for msg in album_messages_sorted]}: {ex}")

async def process_albums(client: Client, channel_id):
    print("🔍 جاري تجميع الألبومات...")
    # التأكد من حل بيانات القناة عبر استدعاء get_chat
    await client.get_chat(channel_id)
    albums = await collect_albums(client, channel_id, FIRST_MSG_ID)
    print(f"تم العثور على {len(albums)} ألبوم.")
    tasks = []
    for media_group_id, messages in albums.items():
        if len(messages) > 1:
            print(f"📂 ألبوم {media_group_id} يحتوي على الرسائل: {[msg.message_id for msg in messages]}")
            tasks.append(transfer_album(client, channel_id, CHANNEL_ID_LOG, messages))
    if tasks:
        await asyncio.gather(*tasks)
    else:
        print("لم يتم العثور على ألبومات.")

async def main():
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
