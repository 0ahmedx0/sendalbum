import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل إعدادات البيئة من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")

# معرفات القنوات وروابط الدعوة
SOURCE_INVITE = os.getenv("CHANNEL_ID", "")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG", "")

# معرف أول وآخر رسالة لتحديد النطاق يدويًا
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", "14356"))  # حدد آخر رسالة هنا

async def collect_and_process_albums(client: Client, chat_id: int, first_msg_id: int, last_msg_id: int, dest_chat_id: int):
    """
    يجمع الرسائل التي تحتوي على media_group_id على دفعات من 500 رسالة، ويرسل كل دفعة مباشرة قبل الانتقال إلى التالية.
    """
    offset_id = first_msg_id - 1  # نبدأ من أول رسالة محددة
    while True:
        messages_batch = []
        albums = {}

        async for message in client.get_chat_history(chat_id, offset_id=offset_id, limit=500):
            if message.id > last_msg_id:
                continue  # تجاوز الرسائل الأحدث من المطلوب
            if message.id < first_msg_id:
                break  # توقف عند الوصول إلى الرسالة الأقدم المحددة
            messages_batch.append(message)
            if message.media_group_id:
                albums.setdefault(message.media_group_id, []).append(message)

        if not messages_batch:
            break  # توقف عند عدم وجود رسائل أخرى للمعالجة
        
        messages_batch.reverse()  # ترتيب الرسائل من الأقدم إلى الأحدث

        # معالجة البيانات (إرسال الألبومات)
        await send_albums(client, albums, dest_chat_id)

        offset_id = messages_batch[-1].id  # تحديث نقطة البداية للدورة التالية

async def send_albums(client: Client, albums: dict, dest_chat_id: int):
    """
    ترسل الألبومات التي تم جمعها.
    """
    for album_id, messages in sorted(albums.items(), key=lambda item: min(msg.id for msg in item[1])):
        print(f"📤 إرسال ألبوم {album_id} يحتوي على {len(messages)} رسالة...")
        media_group = []
        for index, message in enumerate(sorted(messages, key=lambda m: m.id)):
            caption = message.caption if index == 0 else ""
            if message.photo:
                media_group.append(InputMediaPhoto(media=message.photo.file_id, caption=caption))
            elif message.video:
                media_group.append(InputMediaVideo(media=message.video.file_id, caption=caption, supports_streaming=True))
            elif message.document:
                if message.document.mime_type and message.document.mime_type.startswith("video/"):
                    media_group.append(InputMediaVideo(media=message.document.file_id, caption=caption, supports_streaming=True))
                else:
                    media_group.append(InputMediaDocument(media=message.document.file_id, caption=caption))
        
        if media_group:
            try:
                await client.send_media_group(chat_id=dest_chat_id, media=media_group)
                print(f"✅ تم إرسال ألبوم {album_id}")
                await asyncio.sleep(10)  # تأخير 10 ثوانٍ بين كل ألبوم
            except errors.FloodWait as e:
                print(f"⏳ تجاوز الحد: الانتظار {e.value} ثانية...")
                await asyncio.sleep(e.value + 5)
                await client.send_media_group(chat_id=dest_chat_id, media=media_group)
            except Exception as ex:
                print(f"⚠️ خطأ أثناء إرسال الألبوم {album_id}: {ex}")

async def process_albums(client: Client, source_invite: str, dest_invite: str):
    """
    ينضم إلى القناتين، يجمع الألبومات من القناة المصدر، ويرسلها إلى القناة الوجهة على دفعات.
    """
    print("🔍 جاري تجميع الألبومات...")

    # الانضمام إلى القناة المصدر
    try:
        source_chat = await client.join_chat(source_invite)
        print("✅ تم الانضمام للقناة المصدر")
    except errors.UserAlreadyParticipant:
        source_chat = await client.get_chat(source_invite)
        print("✅ الحساب مشارك مسبقاً في القناة المصدر")
    except Exception as e:
        print(f"⚠️ لم يتم الانضمام للقناة المصدر: {e}")
        return

    # الانضمام إلى القناة الوجهة
    try:
        dest_chat = await client.join_chat(dest_invite)
        print("✅ تم الانضمام للقناة الوجهة")
    except errors.UserAlreadyParticipant:
        dest_chat = await client.get_chat(dest_invite)
        print("✅ الحساب مشارك مسبقاً في القناة الوجهة")
    except errors.FloodWait as e:
        print(f"⚠️ Flood Wait: الانتظار {e.value} ثانية قبل إعادة المحاولة.")
        await asyncio.sleep(e.value + 5)
        dest_chat = await client.join_chat(dest_invite)
    except Exception as e:
        print(f"⚠️ لم يتم الانضمام للقناة الوجهة: {e}")
        return

    await collect_and_process_albums(client, source_chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID, dest_chat.id)
    print("✅ تمت معالجة جميع الألبومات!")

async def main():
    async with Client(
        "my_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        print("🚀 العميل متصل بنجاح.")
        await process_albums(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
