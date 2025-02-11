import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# تحميل إعدادات البيئة من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")  # سلسلة الجلسة
# روابط الدعوة للقنوات الخاصة (يجب أن تكون روابط دعوة صالحة)
SOURCE_INVITE = os.getenv("CHANNEL_ID", "")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG", "")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))

async def collect_albums(client: Client, chat_id: int, first_msg_id: int):
    """
    يجمع الرسائل التي تحتوي على media_group_id من تاريخ الدردشة.
    يبدأ من offset = FIRST_MSG_ID - 1 ويتوقف عند وصول رسالة برقم أقل من FIRST_MSG_ID.
    يتم إضافة تأخير 5 ثوانٍ بعد كل دفعة من الرسائل.
    """
    albums = {}
    async for message in client.get_chat_history(chat_id, offset_id=first_msg_id - 1, limit=100):
        await asyncio.sleep(5)  # تأخير 5 ثوانٍ بعد كل دفعة من الرسائل
        if message.id < first_msg_id:
            break
        if message.media_group_id:
            albums.setdefault(message.media_group_id, []).append(message)
    return albums

async def transfer_album(client: Client, source_chat_id: int, dest_chat_id: int, album_messages: list):
    """
    يُرتب الرسائل في الألبوم تصاعدياً (من الأقدم إلى الأحدث) ويُجمع الوسائط في قائمة،
    مع استخدام InputMediaVideo مع supports_streaming في حال كانت الوسائط فيديو.
    ثم يُرسل الألبوم باستخدام send_media_group.
    """
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
        else:
            print(f"⚠️ الرسالة {message.id} لا تحتوي على وسائط قابلة للإرسال ضمن المجموعة.")
    if not media_group:
        print("⚠️ لا توجد وسائط لإرسالها في هذا الألبوم، يتم تخطيه...")
        return
    try:
        await client.send_media_group(chat_id=dest_chat_id, media=media_group)
        print(f"✅ تم إرسال ألبوم الرسائل {[msg.id for msg in album_messages_sorted]} إلى القناة الوجهة")
    except errors.FloodWait as e:
        print(f"⏳ تجاوز الحد: الانتظار {e.value} ثانية...")
        await asyncio.sleep(e.value + 1)
        try:
            await client.send_media_group(chat_id=dest_chat_id, media=media_group)
        except Exception as ex:
            print(f"⚠️ خطأ في إعادة إرسال الألبوم: {ex}")
    except Exception as ex:
        print(f"⚠️ خطأ في إرسال ألبوم الرسائل {[msg.id for msg in album_messages_sorted]}: {ex}")

async def process_albums(client: Client, source_invite: str, dest_invite: str):
    """
    ينضم للقناة المصدر والوجهة باستخدام روابط الدعوة،
    ثم يجمع الألبومات من القناة المصدر ويرسل كل ألبوم على حدة مع انتظار 10 ثوانٍ بين كل إرسال.
    كما يتم ترتيب الألبومات بناءً على أقدم رسالة في كل ألبوم.
    """
    print("🔍 جاري تجميع الألبومات...")

    try:
    dest_chat = await client.join_chat(dest_invite)
    print("✅ تم الانضمام للقناة الوجهة")
except errors.FloodWait as e:
    print(f"⚠️ Flood Wait: الانتظار {e.value} ثانية قبل إعادة المحاولة.")
    await asyncio.sleep(e.value + 5)  # إضافة 5 ثوانٍ إضافية للمساعدة
    dest_chat = await client.join_chat(dest_invite)
except errors.UserAlreadyParticipant:
    dest_chat = await client.get_chat(dest_invite)
    print("✅ الحساب مشارك مسبقاً في القناة الوجهة")
except Exception as e:
    print(f"⚠️ لم يتم الانضمام للقناة الوجهة: {e}")
    return

try:
    dest_chat = await client.join_chat(dest_invite)
    print("✅ تم الانضمام للقناة الوجهة")
except errors.FloodWait as e:
    print(f"⚠️ Flood Wait: الانتظار {e.value} ثانية قبل إعادة المحاولة.")
    await asyncio.sleep(e.value + 5)  # إضافة 5 ثوانٍ إضافية للمساعدة
    dest_chat = await client.join_chat(dest_invite)
except errors.UserAlreadyParticipant:
    dest_chat = await client.get_chat(dest_invite)
    print("✅ الحساب مشارك مسبقاً في القناة الوجهة")
except Exception as e:
    print(f"⚠️ لم يتم الانضمام للقناة الوجهة: {e}")
    return


    albums = await collect_albums(client, source_chat.id, FIRST_MSG_ID)
    print(f"تم العثور على {len(albums)} ألبوم.")
    # ترتيب الألبومات بناءً على أقدم رسالة في كل ألبوم (من الأقدم إلى الأحدث)
    sorted_albums = sorted(albums.items(), key=lambda item: min(msg.id for msg in item[1]))
    for media_group_id, messages in sorted_albums:
        if len(messages) > 1:
            print(f"📂 ألبوم {media_group_id} يحتوي على الرسائل: {[msg.id for msg in messages]}")
            await transfer_album(client, source_chat.id, dest_chat.id, messages)
            await asyncio.sleep(10)  # تأخير 10 ثوانٍ بين إرسال كل ألبوم
        else:
            print(f"⚠️ ألبوم {media_group_id} يحتوي على رسالة واحدة فقط. يتم تخطيه.")

async def main():
    async with Client(
        "my_session",  # يمكنك استخدام أي اسم للجلسة
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        print("🚀 العميل متصل بنجاح.")
        await process_albums(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
