from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
import configparser
import asyncio
import os

# تحميل إعدادات config.ini والبيئة
config = configparser.ConfigParser()
config.read('config.ini')
load_dotenv()

# تفاصيل البوت والقنوات من المتغيرات البيئية
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')  # توكن البوت
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))  # القناة الأصلية التي سنبحث فيها عن الرسائل المكررة
CHANNEL_ID_LOG = int(os.getenv('CHANNEL_ID_LOG', 0))  # القناة التي يتم تحويل الرسائل إليها قبل الحذف
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))  # رقم أول رسالة للبدء منها

# عداد لحساب إجمالي عدد الرسائل المحذوفة
total_deleted_count = 0

def edit_config(progress, current_msg_id, last_msg_id, remaining_msg):
    """
    تحديث ملف الإعدادات لتخزين حالة التقدم
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
    يقوم بتحويل (forward) الرسائل المكررة إلى قناة السجل (log)
    ثم يقوم بحذفها من القناة الأصلية.
    يتم الحذف على دفعات لتفادي حدود Telegram API.
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
            await asyncio.sleep(2)  # تأخير بسيط لتفادي الحظر
        except FloodWaitError as e:
            print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"Error processing messages {chunk}: {e}")

async def update_delete_status(current_msg_id, last_msg_id):
    """
    حساب وتحديث حالة التقدم في عملية الحذف
    """
    if last_msg_id == 0:
        return
    progress = round((current_msg_id / last_msg_id) * 100, 1)
    status_message = (
        f"تقدم عملية الحذف: {progress:.2f}%\n"
        f"معالجة الرسالة ذات المعرف: {current_msg_id}\n"
        f"آخر رسالة للمعالجة: {last_msg_id}\n"
        f"الرسائل المتبقية: {last_msg_id - current_msg_id}\n"
        f"{'-' * 50}"
    )
    edit_config(progress, current_msg_id, last_msg_id, last_msg_id - current_msg_id)
    return status_message

async def search_files(client, channel_id, first_msg_id):
    """
    البحث في القناة عن الرسائل التي تحتوي على ملفات والبحث عن الرسائل المكررة بناءً على اسم الملف.
    قبل حذف الرسائل المكررة، يتم تحويلها إلى قناة السجل.
    """
    global total_deleted_count
    try:
        last_message = await client.get_messages(channel_id, limit=1)
        if not last_message:
            print("خطأ: القناة فارغة أو غير متاحة.")
            return "لم يتم العثور على رسائل."
        
        last_msg_id = last_message[0].id

        # التكرار من الرسالة الأولى حتى آخر رسالة
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
                # البحث عن رسائل مكررة باستخدام اسم الملف
                async for message in client.iter_messages(channel_id, search=query_file_name):
                    if (message.file and hasattr(message.file, 'name') and 
                        message.file.name == query_file_name and 
                        message.id != current_msg_id):
                        duplicate_msg_ids.append(message.id)

                # إذا وُجدت رسائل مكررة، يتم تحويلها ثم حذفها
                if duplicate_msg_ids:
                    await forward_and_delete_messages(client, channel_id, CHANNEL_ID_LOG, current_msg_id, duplicate_msg_ids)
                    await asyncio.sleep(3)  # تأخير بين الدُفعات
            except FloodWaitError as e:
                print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"خطأ في معالجة الرسالة بالمعرف {current_msg_id}: {e}")
            
            # تحديث حالة التقدم
            status = await update_delete_status(current_msg_id, last_msg_id)
            print(status)
            await asyncio.sleep(1)

    except Exception as e:
        print("خطأ حرج في دالة search_files:")
        print(str(e))

    return f"إجمالي عدد الرسائل المكررة المحذوفة: {total_deleted_count}"

# إنشاء عميل البوت باستخدام Telethon وتشغيله بتوكن البوت
client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# معالج أمر /start والذي يعرض أزرار الأوامر للمستخدم
@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    buttons = [
         Button.inline("ابدأ عملية البحث والحذف", b'start_deletion')
    ]
    await event.reply("مرحباً! اختر العملية التي تريد تنفيذها:", buttons=buttons)

# معالج لأزرار الكيبورد (inline) عند الضغط على زر "ابدأ عملية البحث والحذف"
@client.on(events.CallbackQuery(data=b'start_deletion'))
async def callback_handler(event):
    await event.answer("بدأت العملية، الرجاء الانتظار...")
    # بدء عملية البحث والحذف
    result = await search_files(client, CHANNEL_ID, FIRST_MSG_ID)
    # تحديث الرسالة لتظهر للمستخدم انتهاء العملية وتقرير النتيجة
    await event.edit(f"اكتملت العملية.\n{result}")
    # إرسال ملف الإعدادات (config.ini) إلى المحفوظات كمرجع
    file_path = os.path.abspath("config.ini")
    await client.send_file('me', file=file_path, caption=f"إجمالي الرسائل المكررة المحذوفة: {total_deleted_count}")

print("البوت يعمل الآن...")
client.run_until_disconnected()
