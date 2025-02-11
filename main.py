import asyncio
import os
import logging
from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaVideo

# إعداد logging لتسجيل الأحداث مع مستويات مختلفة من التفاصيل
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 🔹 إعدادات البوت: استبدل القيم بالقيم الحقيقية أو عيّنها عبر متغيرات البيئة
API_ID = int(os.getenv("API_ID", 123456))  # استبدل 123456 بـ API_ID الحقيقي
API_HASH = os.getenv("API_HASH")  # ضع API_HASH الحقيقي
SESSION = os.getenv("SESSION", "ضع_الجلسة_هنا")  # استبدل بـ String Session الحقيقي
SOURCE_CHANNEL = os.getenv("CHANNEL_ID", None)  # ضع معرف القناة المصدر (يمكن أن يكون معرف رقمي أو @username)
DESTINATION_CHANNEL = os.getenv("CHANNEL_ID_LOG", None)  # ضع معرف القناة الوجهة (يمكن أن يكون معرف رقمي أو @username)
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", 0))  # ضع معرف أول رسالة (أو 0 لجميع الرسائل)

# التحقق من صحة الإعدادات الأساسية
if not API_HASH:
    logging.error("لم يتم توفير API_HASH. يرجى تعيين متغير البيئة API_HASH.")
    exit(1)
if not SOURCE_CHANNEL:
    logging.error("لم يتم توفير معرف القناة المصدر. يرجى تعيين متغير البيئة CHANNEL_ID.")
    exit(1)
if not DESTINATION_CHANNEL:
    logging.error("لم يتم توفير معرف القناة الوجهة. يرجى تعيين متغير البيئة CHANNEL_ID_LOG.")
    exit(1)

async def collect_albums(client, source_channel, first_msg_id):
    """
    يجمع جميع الرسائل التي تنتمي إلى ألبومات (التي تمتلك الخاصية grouped_id)
    ويعيد قاموساً بالشكل: { grouped_id: [الرسائل] }
    """
    albums = {}
    messages = []

    # تحديث بيانات الدردشات لضمان وجود بيانات الجلسة المحلية
    async for _ in client.get_dialogs():
        pass

    try:
        chat = await client.get_chat(source_channel)
    except Exception as e:
        logging.error(f"خطأ أثناء جلب بيانات القناة {source_channel}: {e}")
        return albums

    async for message in client.get_chat_history(chat_id=chat.id, offset_id=first_msg_id, limit=10000):
        messages.append(message)

    # ترتيب الرسائل تصاعديًا حسب معرف الرسالة
    messages.sort(key=lambda m: m.message_id)

    for message in messages:
        if message.grouped_id:
            albums.setdefault(message.grouped_id, []).append(message)

    return albums

async def forward_albums(client, albums, destination_channel):
    """
    يعيد توجيه الألبومات إلى القناة الوجهة باستخدام send_media_group
    ويضيف تأخير 15 ثانية عند تحويل ألبومات تحتوي على 6 مقاطع أو أكثر
    """
    for grouped_id, messages in albums.items():
        media_group = []

        for message in messages:
            # معالجة مقاطع الفيديو فقط كما هو مطلوب
            if message.video:
                media_group.append(InputMediaVideo(
                    message.video.file_id,
                    caption=message.caption if message.caption else ""
                ))

        if media_group:
            try:
                await client.send_media_group(destination_channel, media_group)
                logging.info(f"✅ تم تحويل الألبوم {grouped_id} بنجاح.")

                # تأخير 15 ثانية إذا كان الألبوم يحتوي على 6 مقاطع أو أكثر لتجنب الحظر
                if len(media_group) >= 6:
                    logging.info("⏳ الانتظار 15 ثانية لتجنب الحظر...")
                    await asyncio.sleep(15)

            except FloodWait as e:
                logging.warning(f"⏳ تم تجاوز الحد! الانتظار {e.value} ثانية...")
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logging.error(f"⚠️ خطأ أثناء إرسال الألبوم {grouped_id}: {e}")

async def main():
    async with Client("bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as app:
        logging.info("🚀 العميل متصل بنجاح.")

        logging.info("🔍 جاري تجميع الألبومات...")
        albums = await collect_albums(app, SOURCE_CHANNEL, FIRST_MSG_ID)

        logging.info(f"📁 تم العثور على {len(albums)} ألبوم. جاري التحويل...")
        await forward_albums(app, albums, DESTINATION_CHANNEL)

if __name__ == "__main__":
    logging.info("🔹 بدء تشغيل البوت باستخدام Pyrogram...")
    asyncio.run(main())
