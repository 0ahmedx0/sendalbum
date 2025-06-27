import asyncio
import os
import random
from dotenv import load_dotenv
from pyrogram import Client, errors

# تحميل متغيرات البيئة
load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
TARGET_CHANNEL = os.getenv("CHANNEL_ID_LOG")
FIRST_MSG_ID = int(os.getenv("FIRST_MSG_ID", "1"))
LAST_MESSAGE_ID = int(os.getenv("LAST_MESSAGE_ID", "0"))

# متغير لتخزين آخر تأخير عشوائي
prev_delay = None

def get_random_delay(min_delay=5, max_delay=50, min_diff=15):
    global prev_delay
    delay = random.randint(min_delay, max_delay)
    while prev_delay is not None and abs(delay - prev_delay) < min_diff:
        delay = random.randint(min_delay, max_delay)
    prev_delay = delay
    return delay

async def fetch_messages_in_range(client: Client, chat_id: int, first_id: int, last_id: int):
    messages = []
    offset_id = last_id + 1
    while True:
        batch = []
        async for message in client.get_chat_history(chat_id, offset_id=offset_id, limit=100):
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

def group_albums(messages):
    albums = {}
    for msg in messages:
        if msg.media_group_id:
            albums.setdefault(msg.media_group_id, []).append(msg)
    return albums

async def pin_albums(client: Client, channel_id: str, albums: dict):
    pinned_count = 0
    for album_id, msgs in albums.items():
        msgs.sort(key=lambda m: m.id)
        first_msg = msgs[0]

        # ⏳ توليد تأخير عشوائي
        delay = get_random_delay()
        print(f"⏳ سيتم الانتظار {delay} ثانية قبل تثبيت الرسالة {first_msg.id}")
        await asyncio.sleep(delay)

        try:
            await client.pin_chat_message(channel_id, first_msg.id, disable_notification=True)
            print(f"📌 تم تثبيت الرسالة {first_msg.id} من الألبوم {album_id}")
            pinned_count += 1
        except errors.FloodWait as e:
            print(f"⏳ FloodWait: الانتظار {e.value} ثانية...")
            await asyncio.sleep(e.value + 5)
            await client.pin_chat_message(channel_id, first_msg.id, disable_notification=True)
        except Exception as e:
            print(f"⚠️ خطأ أثناء التثبيت: {e}")
    print(f"✅ تم تثبيت {pinned_count} ألبوم.")

async def main():
    async with Client("album_pinner", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as client:
        print("🚀 بدء فحص القناة...")
        chat = await client.get_chat(TARGET_CHANNEL)
        messages = await fetch_messages_in_range(client, chat.id, FIRST_MSG_ID, LAST_MESSAGE_ID)
        print(f"📦 تم العثور على {len(messages)} رسالة.")
        albums = group_albums(messages)
        print(f"🗂️ تم العثور على {len(albums)} ألبوم.")
        await pin_albums(client, chat.id, albums)

if __name__ == "__main__":
    asyncio.run(main())
