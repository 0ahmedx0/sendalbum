import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل إعدادات البيئة
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID", "")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG", "")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", "0"))  # آخر رسالة يتم معالجتها يدويًا
BATCH_SIZE = 500  # عدد الرسائل التي يتم معالجتها في كل دفعة

async def collect_albums(client: Client, chat_id: int, first_msg_id: int, last_msg_id: int):
    albums = {}
    offset_id = last_msg_id if last_msg_id else first_msg_id - 1
    while True:
        messages = []
        async for message in client.get_chat_history(chat_id, offset_id=offset_id, limit=BATCH_SIZE):
            messages.append(message)
            await asyncio.sleep(1)  # تقليل الضغط على Telegram
        
        if not messages:
            break  # التوقف إذا لم تعد هناك رسائل جديدة

        offset_id = messages[-1].id - 1  # تحديث معرف الرسالة الأخيرة للدفعة التالية

        for message in messages:
            if message.media_group_id:
                albums.setdefault(message.media_group_id, []).append(message)
    
    return albums

async def transfer_album(client: Client, dest_chat_id: int, album_messages: list):
    album_messages_sorted = sorted(album_messages, key=lambda m: m.id)
    media_group = []
    
    for index, message in enumerate(album_messages_sorted):
        caption = message.caption if (index == 0 and message.caption) else ""
        if message.photo:
            media_group.append(InputMediaPhoto(media=message.photo.file_id, caption=caption))
        elif message.video:
            media_group.append(InputMediaVideo(media=message.video.file_id, caption=caption, supports_streaming=True))
        elif message.document:
            if message.document.mime_type and message.document.mime_type.startswith("video/"):
                media_group.append(InputMediaVideo(media=message.document.file_id, caption=caption, supports_streaming=True))
            else:
                media_group.append(InputMediaDocument(media=message.document.file_id, caption=caption))
    
    if not media_group:
        print("⚠️ لا توجد وسائط قابلة للإرسال، يتم تخطي الألبوم...")
        return
    
    try:
        await client.send_media_group(chat_id=dest_chat_id, media=media_group)
        print(f"✅ تم إرسال ألبوم الرسائل {[msg.id for msg in album_messages_sorted]}")
    except errors.FloodWait as e:
        delay = e.value + 5
        print(f"⏳ تجاوز الحد: الانتظار {delay} ثانية...")
        await asyncio.sleep(delay)
        await client.send_media_group(chat_id=dest_chat_id, media=media_group)
    except Exception as ex:
        print(f"⚠️ خطأ أثناء إرسال الألبوم: {ex}")

async def process_albums(client: Client, source_invite: str, dest_invite: str):
    print("🔍 جاري تجميع الألبومات...")

    try:
        source_chat = await client.join_chat(source_invite)
        print("✅ تم الانضمام للقناة المصدر")
    except errors.UserAlreadyParticipant:
        source_chat = await client.get_chat(source_invite)
    except Exception as e:
        print(f"⚠️ لم يتم الانضمام للقناة المصدر: {e}")
        return

    try:
        dest_chat = await client.join_chat(dest_invite)
        print("✅ تم الانضمام للقناة الوجهة")
    except errors.UserAlreadyParticipant:
        dest_chat = await client.get_chat(dest_invite)
    except errors.FloodWait as e:
        print(f"⚠️ Flood Wait: الانتظار {e.value} ثانية.")
        await asyncio.sleep(e.value + 5)
        dest_chat = await client.join_chat(dest_invite)
    except Exception as e:
        print(f"⚠️ لم يتم الانضمام للقناة الوجهة: {e}")
        return

    albums = await collect_albums(client, source_chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID)
    print(f"تم العثور على {len(albums)} ألبوم.")
    
    sorted_albums = sorted(albums.items(), key=lambda item: min(msg.id for msg in item[1]))
    for media_group_id, messages in sorted_albums:
        if len(messages) > 1:
            print(f"📂 ألبوم {media_group_id} يحتوي على الرسائل: {[msg.id for msg in messages]}")
            await transfer_album(client, dest_chat.id, messages)
            await asyncio.sleep(10)  # تأخير بين عمليات الإرسال
        else:
            print(f"⚠️ ألبوم {media_group_id} يحتوي على رسالة واحدة فقط. يتم تخطيه.")

async def main():
    async with Client("my_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as client:
        print("🚀 العميل متصل بنجاح.")
        await process_albums(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
