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

# 🔹 إعدادات البوت: تأكد من تعيين المتغيرات المناسبة أو تعديل القيم مباشرة
API_ID = int(os.getenv("API_ID", 123456))               # استبدل 123456 بـ API_ID الحقيقي
API_HASH = os.getenv("API_HASH")                        # ضع API_HASH الحقيقي
SESSION = os.getenv("SESSION", "ضع_الجلسة_هنا")         # استبدل بـ String Session الصحيح
SOURCE_CHANNEL = os.getenv("CHANNEL_ID", None)          # معرف القناة المصدر (رقمي أو @username)
DESTINATION_CHANNEL = os.getenv("CHANNEL_ID_LOG", None)   # معرف القناة الوجهة (رقمي أو @username)
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", 0))          # بدء القراءة من رسالة معينة (0 لجميع الرسائل)

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

async def collect_albums(client: Client, source_channel: str, first_msg_id: int) -> dict:
    """
    يجمع جميع الرسائل التي تنتمي إلى ألبومات باستخدام الخاصية media_group_id.
    يُعيد قاموساً بالشكل: { media_group_id: [الرسائل] }
    """
    albums = {}
    messages = []

    # تحديث بيانات الدردشات لضمان جلب المعلومات المحلية
    async for _ in client.get_dialogs():
        pass

    try:
        chat = await client.get_chat(source_channel)
    except Exception as e:
        logging.error(f"خطأ أثناء جلب بيانات القناة {source_channel}: {e}")
        return albums

    # جلب تاريخ الرسائل من القناة
    async for message in client.get_chat_history(chat_id=chat.id, offset_id=first_msg_id, limit=10000):
        messages.append(message)

    # ترتيب الرسائل تصاعدياً حسب معرف الرسالة
    messages.sort(key=lambda m: m.message_id)

    # تجميع الرسائل التي تنتمي إلى ألبومات باستخدام media_group_id
    for message in messages:
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)

    return albums

async def forward_albums(client: Client, albums: dict, destination_channel: str):
    """
    يعيد توجيه الألبومات إلى القناة الوجهة باستخدام send_media_group.
    في حال احتوى الألبوم على 6 وسائط أو أكثر يتم إضافة تأخير لتفادي الحظر.
    """
    for media_group_id, messages in albums.items():
        media_group = []

        for message in messages:
            # معالجة مقاطع الفيديو؛ يمكن تعديل الشرط إذا رغبت في إرسال أنواع وسائط أخرى
            if message.video:
                caption = message.caption if message.caption else ""
                media = InputMediaVideo(
                    media=message.video.file_id,
                    caption=caption
                )
                media_group.append(media)

        if media_group:
            try:
                # إرسال مجموعة الوسائط إلى القناة الوجهة
                await client.send_media_group(destination_channel, media=media_group)
                logging.info(f"✅ تم تحويل الألبوم {media_group_id} بنجاح.")

                # تأخير 15 ثانية إذا كان الألبوم يحتوي على 6 وسائط أو أكثر لتفادي الحظر
                if len(media_group) >= 6:
                    logging.info("⏳ الانتظار 15 ثانية لتجنب الحظر...")
                    await asyncio.sleep(15)

            except FloodWait as e:
                logging.warning(f"⏳ تجاوز الحد! الانتظار {e.x} ثانية...")
                await asyncio.sleep(e.x + 1)
            except Exception as exc:
                logging.error(f"⚠️ خطأ أثناء إرسال الألبوم {media_group_id}: {exc}")

async def main():
    """
    الدالة الرئيسية لإنشاء عميل Pyrogram وتنفيذ عملية جمع وإعادة توجيه الألبومات.
    """
    async with Client("bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as app:
        logging.info("🚀 تم الاتصال بالعميل بنجاح.")
        logging.info("🔍 جاري تجميع الألبومات من القناة المصدر...")

        albums = await collect_albums(app, SOURCE_CHANNEL, FIRST_MSG_ID)
        logging.info(f"📁 تم العثور على {len(albums)} ألبوم. بدء عملية التحويل...")

        await forward_albums(app, albums, DESTINATION_CHANNEL)

if __name__ == "__main__":
    logging.info("🔹 بدء تشغيل البوت باستخدام Pyrogram...")
    asyncio.run(main())
