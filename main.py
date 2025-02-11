import asyncio
import os
from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaVideo

# 🔹 إعدادات البوت
API_ID = int(os.getenv("API_ID", 123456))  # استبدل 123456 بـ API_ID الحقيقي
API_HASH = os.getenv("API_HASH",)  # ضع API_HASH الحقيقي
SESSION = os.getenv("SESSION", "ضع_الجلسة_هنا")  # استبدل بـ String Session الحقيقي
SOURCE_CHANNEL = int(os.getenv("CHANNEL_ID",))  # ضع معرف القناة المصدر
DESTINATION_CHANNEL = int(os.getenv("CHANNEL_ID_LOG",))  # ضع معرف القناة الوجهة
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", 0))  # ضع معرف أول رسالة (أو 0 لجميع الرسائل)

async def collect_albums(client, source_channel, first_msg_id):
    """
    يجمع جميع الرسائل التي تنتمي إلى ألبومات (التي تمتلك الخاصية grouped_id)
    ويعيد قاموساً بالشكل: { grouped_id: [الرسائل] }
    """
    albums = {}
    messages = []

    async for message in client.get_chat_history(chat_id=source_channel, offset_id=first_msg_id, limit=10000):
        messages.append(message)

    # ترتيب الرسائل تصاعديًا حسب معرف الرسالة
    messages = sorted(messages, key=lambda m: m.message_id)

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
            if message.video:
                media_group.append(InputMediaVideo(
                    message.video.file_id,
                    caption=message.caption if message.caption else ""
                ))

        if media_group:
            try:
                await client.send_media_group(destination_channel, media_group)
                print(f"✅ تم تحويل الألبوم {grouped_id} بنجاح")

                # تأخير 15 ثانية إذا كان الألبوم يحتوي على 6 مقاطع أو أكثر
                if len(media_group) >= 6:
                    print("⏳ الانتظار 15 ثانية لتجنب الحظر...")
                    await asyncio.sleep(15)

            except FloodWait as e:
                print(f"⏳ تم تجاوز الحد! الانتظار {e.value} ثانية...")
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                print(f"⚠️ خطأ أثناء إرسال الألبوم {grouped_id}: {e}")

async def main():
    async with Client("bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as app:
        print("🚀 العميل متصل بنجاح.")
        
        print("🔍 جاري تجميع الألبومات...")
        albums = await collect_albums(app, SOURCE_CHANNEL, FIRST_MSG_ID)
        
        print(f"📁 تم العثور على {len(albums)} ألبوم. جاري التحويل...")
        await forward_albums(app, albums, DESTINATION_CHANNEL)

if __name__ == "__main__":
    print("🔹 بدء تشغيل البوت باستخدام Pyrogram...")
    asyncio.run(main())
