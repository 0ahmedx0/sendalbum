from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
import asyncio
import os

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')  
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))         # القناة المصدر
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))   # القناة الوجهة التي سيتم تحويل الرسائل إليها
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))       # معرف أول رسالة للبدء

async def collect_albums(client, channel_id, first_msg_id):
    """
    يجمع جميع الرسائل التي تنتمي إلى ألبومات (بوجود الخاصية grouped_id)
    ويعيد قاموساً بالشكل: { grouped_id: [معرفات الرسائل] }
    """
    albums = {}
    async for message in client.iter_messages(channel_id, min_id=first_msg_id):
        if message.grouped_id:
            albums.setdefault(message.grouped_id, []).append(message.id)
    return albums

async def transfer_album_and_send_original_link(client, source_chat, destination_chat, album_msg_ids):
    """
    يقوم بتحويل ألبوم من الرسائل دون تنزيل الفيديوهات محلياً.
    يتم جمع الكائنات (Document) من كل رسالة في الألبوم واستخدام send_file مع group=True.
    بعد ذلك، يتم إرسال رابط الرسالة الأصلية (أول رسالة في الألبوم) إلى القناة الوجهة.
    """
    # الرسالة الأولى تعتبر الأصلية
    original_msg_id = album_msg_ids[0]
    files = []
    for msg_id in album_msg_ids:
        try:
            msg = await client.get_messages(source_chat, ids=msg_id)
            if msg and msg.media and hasattr(msg.media, 'document'):
                # جمع الكائن Document الموجود في الرسالة
                files.append(msg.media.document)
            else:
                print(f"⚠️ الرسالة {msg_id} لا تحتوي على وثيقة مناسبة.")
        except Exception as e:
            print(f"⚠️ خطأ في جلب الرسالة {msg_id}: {e}")

    if not files:
        print("⚠️ لا توجد ملفات لإرسالها في هذا الألبوم، يتم تخطيه...")
        return

    try:
        # إرسال الألبوم باستخدام send_file مع group=True (يعادل send_media_group)
        await client.send_file(destination_chat, file=files, group=True)
        print(f"✅ تم إرسال ألبوم الرسائل {album_msg_ids} إلى القناة الوجهة")
    except FloodWaitError as e:
        print(f"⏳ تجاوز الحد: الانتظار {e.seconds} ثانية...")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        print(f"⚠️ خطأ في إرسال ألبوم الرسائل {album_msg_ids}: {e}")

    # تكوين رابط الرسالة الأصلية؛ نفترض أن معرف القناة يبدأ بـ -100، لذا نزيلها للحصول على الرابط الصحيح
    src_str = str(source_chat)
    if src_str.startswith("-100"):
        link_channel = src_str[4:]
    else:
        link_channel = src_str
    original_link = f"https://t.me/c/{link_channel}/{original_msg_id}"
    try:
        await client.send_message(destination_chat, f"📌 الرسالة الأصلية: {original_link}")
        print(f"🔗 تم إرسال رابط الرسالة الأصلية: {original_link}")
    except Exception as e:
        print(f"⚠️ خطأ في إرسال رابط الرسالة الأصلية: {e}")

async def process_albums(client, channel_id):
    """
    يجمع ألبومات الرسائل من القناة المصدر، ثم ينقل كل ألبوم باستخدام الدالة transfer_album_and_send_original_link.
    """
    print("🔍 جاري تجميع الألبومات...")
    albums = await collect_albums(client, channel_id, FIRST_MSG_ID)
    print(f"تم العثور على {len(albums)} ألبوم.")
    
    tasks = []
    for grouped_id, msg_ids in albums.items():
        if len(msg_ids) > 1:  # نعتبر الألبوم إذا كان يحتوي على أكثر من رسالة
            print(f"📂 ألبوم {grouped_id} يحتوي على الرسائل: {msg_ids}")
            tasks.append(transfer_album_and_send_original_link(client, channel_id, CHANNEL_ID_LOG, msg_ids))
    if tasks:
        await asyncio.gather(*tasks)
    else:
        print("لم يتم العثور على ألبومات.")

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 العميل متصل بنجاح.")
        await process_albums(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
