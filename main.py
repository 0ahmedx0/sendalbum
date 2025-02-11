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
SESSION = os.getenv('SESSION')           # سلسلة جلسة المستخدم (StringSession)
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))         # القناة الأصلية التي يتم البحث فيها
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0)) # القناة التي يتم تحويل الرسائل إليها (قناة السجل)
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))     # معرف أول رسالة يبدأ منها البحث

# عداد لحساب إجمالي عدد الرسائل المحذوفة
total_deleted_count = 0

def edit_config(progress, current_msg_id, last_msg_id, remaining_msg):
    """
    تحديث ملف config.ini بحالة العملية.
    """
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

async def forward_and_delete_messages(client, source_chat, destination_chat, query_msg_id, duplicate_msg_ids):
    """
    يقوم بتحويل الرسائل المكررة إلى قناة السجل ثم حذفها من القناة الأصلية.
    يتم تقسيم الرسائل إلى دفعات لتفادي حدود Telegram API.
    """
    global total_deleted_count
    chunk_size = 99  # حد Telegram API لكل دفعة
    for i in range(0, len(duplicate_msg_ids), chunk_size):
        chunk = duplicate_msg_ids[i:i + chunk_size]
        try:
            # تحويل الرسائل إلى قناة السجل
            await client.forward_messages(destination_chat, chunk, from_chat=source_chat)
            # حذف الرسائل من القناة الأصلية
            await client.delete_messages(source_chat, chunk)
            total_deleted_count += len(chunk)
            print(f"ID {query_msg_id}: Forwarded and deleted duplicate messages {chunk}")
            await asyncio.sleep(2)
        except FloodWaitError as e:
            print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"Error processing messages {chunk}: {e}")

async def update_delete_status(current_msg_id, last_msg_id):
    """
    حساب وتحديث حالة التقدم في عملية الحذف.
    """
    if last_msg_id == 0:
        return
    progress = round((current_msg_id / last_msg_id) * 100, 1)
    status_message = (
        f"تقدم عملية الحذف: {progress:.2f}%\n"
        f"معالجة الرسالة ذات المعرف: {current_msg_id}\n"
        f"آخر رسالة للمعالجة: {last_msg_id}\n"
        f"الرسائل المتبقية: {last_msg_id - current_msg_id}\n"
        f"{'-'*50}"
    )
    edit_config(progress, current_msg_id, last_msg_id, last_msg_id - current_msg_id)
    return status_message

async def search_files(client, channel_id, first_msg_id):
    """
    البحث في القناة عن الرسائل التي تحتوي على ملفات ثم تحديد الرسائل المكررة بناءً على اسم الملف.
    يتم تحويل الرسائل المكررة إلى قناة السجل قبل حذفها من القناة الأصلية.
    """
    global total_deleted_count
    try:
        last_message = await client.get_messages(channel_id, limit=1)
        if not last_message:
            print("خطأ: القناة فارغة أو غير متاحة.")
            return "لم يتم العثور على رسائل."
        last_msg_id = last_message[0].id

        # التكرار من الرسالة الأولى حتى آخر رسالة في القناة
        for current_msg_id in range(first_msg_id, last_msg_id + 1):
            try:
                specific_message = await client.get_messages(channel_id, ids=current_msg_id)
                if not specific_message or not specific_message.message:
                    continue

                # استخراج اسم الملف (إن وجد)
                query_file_name = None
                if specific_message.media and hasattr(specific_message.media, 'document'):
                    for attribute in specific_message.media.document.attributes:
                        if isinstance(attribute, DocumentAttributeFilename):
                            query_file_name = attribute.file_name
                            break

                if not query_file_name:
                    continue

                duplicate_msg_ids = []
                # البحث عن الرسائل المكررة باستخدام اسم الملف
                async for message in client.iter_messages(channel_id, search=query_file_name):
                    if (message.file and hasattr(message.file, 'name') and 
                        message.file.name == query_file_name and 
                        message.id != current_msg_id):
                        duplicate_msg_ids.append(message.id)

                if duplicate_msg_ids:
                    await forward_and_delete_messages(client, channel_id, CHANNEL_ID_LOG, current_msg_id, duplicate_msg_ids)
                    await asyncio.sleep(3)
            except FloodWaitError as e:
                print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"خطأ في معالجة الرسالة بالمعرف {current_msg_id}: {e}")
            
            status = await update_delete_status(current_msg_id, last_msg_id)
            print(status)
            await asyncio.sleep(1)

    except Exception as e:
        print("خطأ حرج في دالة search_files:")
        print(str(e))

    return f"إجمالي عدد الرسائل المكررة المحذوفة: {total_deleted_count}"

async def main():
    # إنشاء عميل باستخدام حساب المستخدم عبر StringSession
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        print("العميل متصل بنجاح.")
        # بدء عملية البحث والحذف
        result = await search_files(client, CHANNEL_ID, FIRST_MSG_ID)
        # إرسال ملف الإعدادات إلى المحفوظات (Saved Messages)
        file_path = os.path.abspath("config.ini")
        await client.send_file('me', file=file_path, caption=f"إجمالي الرسائل المكررة المحذوفة: {total_deleted_count}")
        print(result)

if __name__ == '__main__':
    print("البرنامج بدأ...")
    asyncio.run(main())
