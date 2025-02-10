from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError
import configparser
import os
import re
import asyncio
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()

# الثوابت
CHANNEL_ID_LOG = -1002432026957  # إيدي قناة اللوج الثابتة
config = configparser.ConfigParser()

# إنشاء ملف التكوين إذا لم يكن موجودًا
if not os.path.exists('config.ini'):
    config['SETTINGS'] = {
        'CHANNEL_ID': '',
        'FIRST_MSG_ID': '0',
        'CHECK_SIZE': 'yes',
        'CHECK_HASH': 'no',
        'KEEP_POLICY': 'oldest'
    }
    with open('config.ini', 'w') as f:
        config.write(f)
else:
    config.read('config.ini')

app = Client(
    "bot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN")
)

# دالة الاستماع المخصصة
async def listen(client, filters, timeout=300):
    future = client.loop.create_future()
    
    @client.on_message(filters)
    async def handler(_, message):
        if not future.done():
            future.set_result(message)
    
    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        client.remove_handler(handler)

# استخراج إيدي القناة من الرابط
def extract_channel_id(text):
    if text.startswith("https://t.me/"):
        username = text.split("/")[-1]
        try:
            return app.get_chat(username).id
        except Exception:
            return None
    return int(text) if text.lstrip('-').isdigit() else None

# استخراج إيدي الرسالة من الرابط
def extract_message_id(text):
    if "https://t.me/" in text:
        return int(text.split("/")[-1])
    return int(text) if text.isdigit() else 0

# تسجيل الرسائل المحذوفة
async def log_deletion(message):
    try:
        log_text = f"🗑 **تم حذف رسالة مكررة**\n\n"
        log_text += f"📄 اسم الملف: `{message.document.file_name}`\n"
        log_text += f"🆔 ايدي الرسالة: `{message.id}`\n"
        log_text += f"📅 التاريخ: `{message.date}`\n"
        await app.send_message(CHANNEL_ID_LOG, log_text)
    except Exception as e:
        print(f"فشل في التسجيل: {e}")

@app.on_message(filters.command("start"))
async def start(client, message):
    # طلب إيدي القناة
    await message.reply("📤 أرسل إيدي القناة أو رابطها:")
    channel_response = await listen(client, 
        filters.text & filters.user(message.from_user.id),
        timeout=300
    )
    
    if not channel_response:
        return await message.reply("⏰ انتهى وقت الإدخال!")
    
    # طلب رابط الرسالة الأولى
    await message.reply("📩 أرسل رابط الرسالة الأولى:")
    first_msg_response = await listen(client,
        filters.text & filters.user(message.from_user.id),
        timeout=300
    )
    
    # حفظ الإعدادات
    channel_id = extract_channel_id(channel_response.text)
    first_msg_id = extract_message_id(first_msg_response.text)
    
    config['SETTINGS'] = {
        'CHANNEL_ID': str(channel_id),
        'FIRST_MSG_ID': str(first_msg_id),
        'CHECK_SIZE': 'yes',
        'CHECK_HASH': 'no',
        'KEEP_POLICY': 'oldest'
    }
    with open('config.ini', 'w') as f:
        config.write(f)
    
    await message.reply(
        f"✅ تم الإعداد بنجاح!\n"
        f"القناة: `{channel_id}`\n"
        f"الرسالة الأولى: `{first_msg_id}`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بدء التنظيف", callback_data="start_clean")]
        ])
    )

@app.on_callback_query(filters.regex("start_clean"))
async def start_cleaning(client, callback_query):
    try:
        channel_id = int(config['SETTINGS']['CHANNEL_ID'])
        first_msg_id = int(config['SETTINGS']['FIRST_MSG_ID'])
        
        # الحصول على آخر رسالة
        last_msg = (await client.get_chat_history(channel_id, limit=1))[0]
        
        # بدء عملية التنظيف
        progress_msg = await callback_query.message.reply("⏳ جاري البدء في العملية...")
        
        async for msg in client.get_chat_history(channel_id):
            if msg.id < first_msg_id:
                break
            
            if msg.document:
                duplicates = []
                async for m in client.search_messages(channel_id, query=msg.document.file_name):
                    if m.id != msg.id and m.document.file_name == msg.document.file_name:
                        if config.getboolean('SETTINGS', 'CHECK_SIZE') and m.document.file_size != msg.document.file_size:
                            continue
                        duplicates.append(m.id)
                
                if duplicates:
                    await client.delete_messages(channel_id, duplicates)
                    for dup_id in duplicates:
                        dup_msg = await client.get_messages(channel_id, dup_id)
                        await log_deletion(dup_msg)
                    
                    await progress_msg.edit_text(
                        f"🚮 تم حذف {len(duplicates)} رسائل مكررة\n"
                        f"🔄 جاري متابعة العملية..."
                    )
        
        await progress_msg.edit_text("✅ اكتملت العملية بنجاح!")
        
    except FloodWait as e:
        await progress_msg.edit_text(f"⏳ يرجى الانتظار {e.value} ثانية")
        await asyncio.sleep(e.value)
        await start_cleaning(client, callback_query)
    except Exception as e:
        await callback_query.message.reply(f"❌ فشلت العملية: {str(e)}")

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
