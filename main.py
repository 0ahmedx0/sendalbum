import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام من البيئة
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")  # يمكن أن تكون سلسلة الجلسة أو اسم ملف الجلسة
SOURCE_CHANNEL = int(os.getenv("CHANNEL_ID", 0))       # القناة المصدر
DESTINATION_CHANNEL = int(os.getenv("CHANNEL_ID_LOG", 0))  # القناة الوجهة
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", 0))         # معرف أول رسالة للبدء

async def collect_albums(client, source_channel, first_msg_id):
    """
    يجمع الرسائل التي تنتمي إلى ألبومات (التي تمتلك الخاصية grouped_id)
    ويعيد قاموساً بالشكل: { grouped_id: [الرسائل] }
    """
    albums = {}
    # استخدم iter_history للحصول على الرسائل ابتداءً من FIRST_MSG_ID، مع reverse=True لضمان الترتيب الصحيح
    async for message in client.iter_history(source_channel, offset_id=first_msg_id, reverse=True):
        if message.grouped_id:
            albums.setdefault(message.grouped_id, []).append(message)
    return albums

async def transfer_album(client, album_messages):
    """
    يقوم بنقل ألبوم الرسائل إلى القناة الوجهة باستخدام send_media_group.
    لا يتم إرسال رابط الرسالة الأصلية.
    """
    media_group = []
    # إعداد قائمة الوسائط اعتماداً على نوع الرسالة
    for msg in album_messages:
        if msg.photo:
            media_group.append(InputMediaPhoto(media=msg.photo.file_id, caption=msg.caption or ""))
        elif msg.video:
            media_group.append(InputMediaVideo(media=msg.video.file_id, caption=msg.caption or ""))
        else:
            print(f"⚠️ الرسالة {msg.message_id} ليست من نوع photo أو video، يتم تجاهلها.")
    
    if not media_group:
        print("⚠️ لا توجد وسائط مناسبة في هذا الألبوم، يتم تخطيه...")
        return

    try:
        # إرسال الألبوم باستخدام send_media_group
        await client.send_media_group(chat_id=DESTINATION_CHANNEL, media=media_group)
        print(f"✅ تم إرسال ألبوم يحتوي على {len(media_group)} وسائط إلى القناة الوجهة.")
    except Exception as e:
        print(f"⚠️ خطأ في إرسال الألبوم: {e}")

async def process_albums(client, source_channel):
    """
    يجمع ألبومات الرسائل من القناة المصدر ثم ينقل كل ألبوم باستخدام transfer_album.
    يتم إضافة تأخير لمدة 15 ثانية بعد كل 6 ألبومات لتجنب الحظر.
    """
    print("🔍 جاري تجميع الألبومات...")
    albums = await collect_albums(client, source_channel, FIRST_MSG_ID)
    print(f"تم العثور على {len(albums)} ألبوم.")
    counter = 0
    for grouped_id, messages in albums.items():
        if len(messages) > 1:
            print(f"📂 ألبوم {grouped_id} يحتوي على {len(messages)} رسالة.")
            await transfer_album(client, messages)
            counter += 1
            if counter % 6 == 0:
                print("⏳ انتظر 15 ثانية لتجنب الحظر...")
                await asyncio.sleep(15)
        else:
            print(f"📄 رسالة فردية (غير ألبوم) يتم تجاهلها.")

async def main():
    async with Client(SESSION, api_id=API_ID, api_hash=API_HASH) as app:
        print("🚀 العميل متصل بنجاح.")
        await process_albums(app, SOURCE_CHANNEL)

if __name__ == "__main__":
    print("🔹 بدء تشغيل البوت باستخدام Pyrogram...")
    asyncio.run(main())
