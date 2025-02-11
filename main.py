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
            print(f"✅ Forwarded and deleted duplicate messages {chunk}")
            await asyncio.sleep(2)
        except FloodWaitError as e:
            print(f"⏳ تم تجاوز الحد! الانتظار {e.seconds} ثانية...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"⚠️ Error processing messages {chunk}: {e}")

async def update_delete_status(current_msg_id, last_msg_id):
    if last_msg_id == 0:
        return
    progress = round((current_msg_id / last_msg_id) * 100, 1)
    edit_config(progress, current_msg_id, last_msg_id, last_msg_id - current_msg_id)
    print(f"📌 تقدم العملية: {progress:.2f}% - معالجة الرسالة ذات المعرف: {current_msg_id}")

async def search_files(client, channel_id, first_msg_id):
    """
    البحث عن الرسائل التي تحتوي على ملفات ثم تحديد الرسائل المكررة بناءً على الحجم فقط.
    يتم تحويل الرسائل المكررة إلى قناة السجل قبل حذفها من القناة الأصلية.
    """
    global total_deleted_count
    try:
        last_message = await client.get_messages(channel_id, limit=1)
        if not last_message:
            print("🚫 خطأ: القناة فارغة أو غير متاحة.")
            return "لم يتم العثور على رسائل."
        last_msg_id = last_message[0].id

        for current_msg_id in range(first_msg_id, last_msg_id + 1):
            try:
                specific_message = await client.get_messages(channel_id, ids=current_msg_id)
                if not specific_message or not specific_message.media:
                    continue

                # استخراج حجم الملف فقط
                query_file_size = None
                query_file_name = "غير معروف"
                
                if hasattr(specific_message.media, 'document'):
                    query_file_size = specific_message.media.document.size
                    for attribute in specific_message.media.document.attributes:
                        if isinstance(attribute, DocumentAttributeFilename):
                            query_file_name = attribute.file_name  # الاحتفاظ باسم الملف للطباعة فقط
                            break

                if query_file_size is None:
                    continue

                duplicate_msg_ids = []
                async for message in client.iter_messages(channel_id):
                    if (message.file and hasattr(message.file, 'size') and 
                        message.file.size == query_file_size and  # التحقق من الحجم فقط
                        message.id != current_msg_id):

                        duplicate_msg_ids.append(message.id)

                if duplicate_msg_ids:
                    print(f"📂 ملف مكرر بحجم {query_file_size} باختيار الرسالة {current_msg_id} (اسم الملف: {query_file_name})")
                    await forward_and_delete_messages(client, channel_id, CHANNEL_ID_LOG, duplicate_msg_ids)
                    await asyncio.sleep(3)
            except FloodWaitError as e:
                print(f"⏳ تم تجاوز الحد! الانتظار {e.seconds} ثانية...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"⚠️ خطأ في معالجة الرسالة بالمعرف {current_msg_id}: {e}")
            
            await update_delete_status(current_msg_id, last_msg_id)
            await asyncio.sleep(1)

    except Exception as e:
        print("❌ خطأ حرج في دالة search_files:")
        print(str(e))

    return f"📌 إجمالي عدد الرسائل المكررة المحذوفة: {total_deleted_count}"

async def main():
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("🚀 العميل متصل بنجاح.")
        result = await search_files(client, CHANNEL_ID, FIRST_MSG_ID)
        file_path = os.path.abspath("config.ini")
        await client.send_file('me', file=file_path, caption=f"📌 إجمالي الرسائل المكررة المحذوفة: {total_deleted_count}")
        print(result)

if __name__ == '__main__':
    print("🔹 بدء تشغيل البوت...")
    asyncio.run(main())
