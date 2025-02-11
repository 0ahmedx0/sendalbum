from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
import asyncio
import os

# تحميل إعدادات البيئة
load_dotenv()

# إعدادات تيليجرام
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')  
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))  
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))  

# قائمة لحساب الرسائل المحذوفة
total_deleted_count = 0

async def collect_files(client, channel_id, first_msg_id):
    """
    يجمع جميع الملفات وأحجامها في قاموس { الحجم: {معرفات الرسائل} }
    """
    file_dict = {}  # { حجم الملف: {معرفات الرسائل} }

    async for message in client.iter_messages(channel_id, min_id=first_msg_id):
        if message.file and hasattr(message.file, 'size'):
            file_size = message.file.size
            file_dict.setdefault(file_size, set()).add(message.id)

    return file_dict

async def forward_and_delete_messages(client, source_chat, destination_chat, duplicate_msg_ids):
    """
    ينقل ويحذف الرسائل المكررة
    """
    global total_deleted_count
    if not duplicate_msg_ids:
        return

    chunk_size = 99
    tasks = []

    for i in range(0, len(duplicate_msg_ids), chunk_size):
        chunk = list(duplicate_msg_ids)[i:i + chunk_size]
        tasks.append(asyncio.create_task(client.forward_messages(destination_chat, chunk, from_peer=source_chat)))
        tasks.append(asyncio.create_task(client.delete_messages(source_chat, chunk)))
        total_deleted_count += len(chunk)

    await asyncio.gather(*tasks)
    print(f"✅ تم حذف {total_deleted_count} رسالة مكررة.")

async def delete_duplicates(client, channel_id):
    """
    يبحث عن الملفات المكررة حسب الحجم ويحذفها
    """
    global total_deleted_count
    print("🔍 جاري تجميع الملفات...")

    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    delete_tasks = []

    for file_size, msg_ids in file_dict.items():
        if len(msg_ids) > 1:  # إذا وجد أكثر من رسالة بنفس الحجم
            msg_ids = sorted(msg_ids)  # لضمان الاحتفاظ بأقدم نسخة
            print(f"📂 ملفات مكررة بحجم {file_size}, سيتم حذف {len(msg_ids)-1} نسخة.")
            delete_tasks.append(forward_and_delete_messages(client, channel_id, CHANNEL_ID_LOG, list(msg_ids[1:])))

    await asyncio.gather(*delete_tasks)
    print(f"📌 إجمالي الرسائل المحذوفة: {total_deleted_count}")

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 العميل متصل بنجاح.")
        await delete_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
