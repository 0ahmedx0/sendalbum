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
    يجمع جميع الملفات وأحجامها في قاموس { الحجم: [معرفات الرسائل] }
    """
    file_dict = {}  # { حجم الملف: [معرفات الرسائل] }

    async for message in client.iter_messages(channel_id, min_id=first_msg_id):
        if message.file and hasattr(message.file, 'size'):
            file_size = message.file.size
            if file_size in file_dict:
                file_dict[file_size].append(message.id)
            else:
                file_dict[file_size] = [message.id]

    return file_dict

async def forward_and_delete_messages(client, source_chat, destination_chat, duplicate_msg_ids):
    """
    ينقل ويحذف الرسائل المكررة مع تأخير 5 ثوانٍ بعد كل تحويل فقط.
    """
    global total_deleted_count
    chunk_size = 99  # الحد الأقصى للرسائل التي يمكن معالجتها في دفعة واحدة

    for i in range(0, len(duplicate_msg_ids), chunk_size):
        chunk = duplicate_msg_ids[i:i + chunk_size]
        try:
            await client.forward_messages(destination_chat, chunk, from_peer=source_chat)
            print(f"✅ Forwarded duplicate messages {chunk}")
            await asyncio.sleep(5)  # تأخير 5 ثوانٍ بعد كل تحويل
            await client.delete_messages(source_chat, chunk)
            total_deleted_count += len(chunk)
            print(f"🗑 Deleted duplicate messages {chunk}")
        except FloodWaitError as e:
            print(f"⏳ تم تجاوز الحد! الانتظار {e.seconds} ثانية...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"⚠️ خطأ في حذف الرسائل {chunk}: {e}")

async def delete_duplicates(client, channel_id):
    """
    يبحث عن الملفات المكررة حسب الحجم ويحذفها
    """
    global total_deleted_count
    print("🔍 جاري تجميع الملفات...")

    file_dict = await collect_files(client, channel_id, FIRST_MSG_ID)
    
    for file_size, msg_ids in file_dict.items():
        if len(msg_ids) > 1:  # إذا وجد أكثر من رسالة بنفس الحجم
            print(f"📂 ملفات مكررة بحجم {file_size} باختيار {msg_ids[0]}")
            await forward_and_delete_messages(client, channel_id, CHANNEL_ID_LOG, msg_ids[1:])
    
    print(f"📌 إجمالي الرسائل المحذوفة: {total_deleted_count}")

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 العميل متصل بنجاح.")
        await delete_duplicates(client, CHANNEL_ID)

if __name__ == '__main__':
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
