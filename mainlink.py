import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, errors

# تحميل الإعدادات من ملف .env
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
SOURCE_INVITE = os.getenv("CHANNEL_ID")
DEST_INVITE = os.getenv("CHANNEL_ID_LOG")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", ""))
BATCH_SIZE = 2000  # حجم كل دفعة من الرسائل

async def get_chat_safe(client, identifier):
    try:
        if identifier.startswith("-100"):
            return await client.get_chat(identifier)
        else:
            return await client.join_chat(identifier)
    except errors.UserAlreadyParticipant:
        return await client.get_chat(identifier)

async def fetch_messages_in_range(client: Client, chat_id: int, first_id: int, last_id: int):
    messages = []
    offset_id = last_id + 1
    while True:
        batch = []
        async for message in client.get_chat_history(chat_id, offset_id=offset_id, limit=1000):
            if message.id < first_id:
                break
            batch.append(message)
        if not batch:
            break
        messages.extend(batch)
        offset_id = batch[-1].id
        if batch[-1].id < first_id:
            break
    messages = [m for m in messages if m.id >= first_id]
    messages.sort(key=lambda m: m.id)
    return messages

def chunk_messages(messages, chunk_size):
    for i in range(0, len(messages), chunk_size):
        yield messages[i:i+chunk_size]

def group_albums(messages):
    albums = {}
    for msg in messages:
        if msg.media_group_id:
            albums.setdefault(msg.media_group_id, []).append(msg)
    return albums

def build_link(chat_id, msg_id):
    src = str(chat_id)
    if src.startswith("-100"):
        channel_part = src[4:]
    else:
        channel_part = src
    return f"https://t.me/c/{channel_part}/{msg_id}"

async def process_channel(client: Client, source_invite: str, dest_invite: str):
    source_chat = await get_chat_safe(client, source_invite)
    print(f"✅ تم الاتصال بالقناة المصدر: {source_chat.id}")

    dest_chat = await get_chat_safe(client, dest_invite)
    print(f"✅ تم الاتصال بالقناة الوجهة: {dest_chat.id}")

    print("🔍 جاري جلب جميع الرسائل في النطاق المحدد...")
    all_messages = await fetch_messages_in_range(client, source_chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID)
    print(f"🔍 تم جلب {len(all_messages)} رسالة ضمن النطاق")

    album_links = []
    for batch in chunk_messages(all_messages, BATCH_SIZE):
        albums = group_albums(batch)
        sorted_albums = sorted(albums.items(), key=lambda item: min(m.id for m in item[1]))
        for album_id, msgs in sorted_albums:
            first_msg_id = msgs[0].id
            link = build_link(source_chat.id, first_msg_id)
            album_links.append(link)
            print(f"🔗 تم استخراج رابط ألبوم: {link}")

            if len(album_links) % 20 == 0:
                start_index = len(album_links) - 20
                numbered_links = [
                    f"{start_index + i + 1}. {link}\n"
                    for i, link in enumerate(album_links[-20:])
                ]
                text = "\n".join(numbered_links)
                await client.send_message(dest_chat.id, text)
                print(f"📤 تم إرسال دفعة روابط ({len(album_links)}) إلى القناة الوجهة")
                await asyncio.sleep(5)  # ← تأخير 5 ثواني بعد كل دفعة

    # إرسال المتبقي إن وجد
    remaining = len(album_links) % 20
    if remaining:
        start_index = len(album_links) - remaining
        numbered_links = [
            f"{start_index + i + 1}. {link}\n"
            for i, link in enumerate(album_links[-remaining:])
        ]
        text = "\n".join(numbered_links)
        await client.send_message(dest_chat.id, text)
        print(f"📤 تم إرسال آخر دفعة روابط ({remaining}) إلى القناة الوجهة")

    print("✅ اكتملت العملية بنجاح!")

async def main():
    async with Client(
        name="media_transfer_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION
    ) as client:
        print("🚀 بدء تشغيل البوت...")
        await process_channel(client, SOURCE_INVITE, DEST_INVITE)

if __name__ == "__main__":
    print("🔹 جاري تهيئة النظام...")
    asyncio.run(main())
