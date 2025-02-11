from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from dotenv import load_dotenv
import configparser
import asyncio
import os

# تحميل إعدادات البيئة وملف الإعدادات
load_dotenv()
config = configparser.ConfigParser()
config.read('config.ini')

# قراءة المتغيرات البيئية اللازمة لحساب المستخدم
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')  # سلسلة جلسة المستخدم (StringSession)
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  # القناة الأصلية
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))  # القناة التي يتم تحويل الرسائل إليها
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))  # معرف أول رسالة

# عداد لحساب إجمالي عدد الرسائل المحذوفة
total_deleted_count = 0

def edit_config(progress, current_msg_id, last_msg_id, remaining_msg):
    config.read('config.ini')
    if "status" not in config:
        config.add_section("status")
    config["status"]["progress"] = str(progress)
    config["status"]["current_msg_id"] = str(current_msg_id)
    config["status"]["last_msg_id"] = str(last_msg_id)
    config["status"]["remaining_msg"] = str(remaining_msg)
    config["status"]["total_delete_count"] = str(total_deleted_count)
    with open('config.ini', 'w') as configfile:
        config.write(configfile)

async def forward_and_delete_messages(client, source_chat, destination_chat, duplicate_msg_ids):
    global total_deleted_count
    chunk_size = 99
    for i in range(0, len(duplicate_msg_ids), chunk_size):
        chunk = duplicate_msg_ids[i:i + chunk_size]
        try:
            await client.forward_messages(destination_chat, chunk, from_peer=source_chat)
            await client.delete_messages(source_chat, chunk)
            total_deleted_count += len(chunk)
            print(f"Forwarded and deleted duplicate messages {chunk}")
            await asyncio.sleep(2)
        except FloodWaitError as e:
            print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"Error processing messages {chunk}: {e}")

async def update_delete_status(current_msg_id, last_msg_id):
    if last_msg_id == 0:
        return
    progress = round((current_msg_id / last_msg_id) * 100, 1)
    edit_config(progress, current_msg_id, last_msg_id, last_msg_id - current_msg_id)
    print(f"Progress: {progress:.2f}% - Processing message ID: {current_msg_id}")

async def search_files(client, channel_id, first_msg_id):
    global total_deleted_count
    try:
        last_message = await client.get_messages(channel_id, limit=1)
        if not last_message:
            print("Error: Channel is empty or unavailable.")
            return "No messages found."
        last_msg_id = last_message[0].id

        for current_msg_id in range(first_msg_id, last_msg_id + 1):
            try:
                specific_message = await client.get_messages(channel_id, ids=current_msg_id)
                if not specific_message or not specific_message.message:
                    continue
                
                query_file_name = None
                if specific_message.media and hasattr(specific_message.media, 'document'):
                    for attribute in specific_message.media.document.attributes:
                        if isinstance(attribute, DocumentAttributeFilename):
                            query_file_name = attribute.file_name
                            break
                
                if not query_file_name:
                    continue
                
                duplicate_msg_ids = []
                async for message in client.iter_messages(channel_id, search=query_file_name):
                    if message.file and hasattr(message.file, 'name') and message.file.name == query_file_name and message.id != current_msg_id:
                        duplicate_msg_ids.append(message.id)
                
                if duplicate_msg_ids:
                    await forward_and_delete_messages(client, channel_id, CHANNEL_ID_LOG, duplicate_msg_ids)
                    await asyncio.sleep(3)
            except FloodWaitError as e:
                print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"Error processing message ID {current_msg_id}: {e}")
            
            await update_delete_status(current_msg_id, last_msg_id)
            await asyncio.sleep(1)
    except Exception as e:
        print("Critical error in search_files:", str(e))
    return f"Total duplicate messages deleted: {total_deleted_count}"

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("Client connected successfully.")
        result = await search_files(client, CHANNEL_ID, FIRST_MSG_ID)
        file_path = os.path.abspath("config.ini")
        await client.send_file('me', file=file_path, caption=f"Total deleted messages: {total_deleted_count}")
        print(result)

if __name__ == '__main__':
    print("Starting bot...")
    asyncio.run(main())
