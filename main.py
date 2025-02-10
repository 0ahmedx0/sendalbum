from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError
import re
import asyncio
import os
import configparser
from urllib.parse import urlparse

# ثوابت البوت
CHANNEL_ID_LOG = -1002432026957  # ضع هنا ايدي قناة اللوج الثابتة
config = configparser.ConfigParser()
config.read('config.ini')

app = Client(
    "bot",
    api_id=os.getenv('23151406'),
    api_hash=os.getenv('0893a87614fae057c8efe7b85114f45a'),
    bot_token=os.getenv('8074305463:AAGTS-J1ptk-q-k1m07ejzwPHCPWZhlLNyI')
)

async def request_channel_info(client, message):
    # طلب ايدي القناة
    await client.send_message(
        message.chat.id,
        "⏳ يرجى إرسال ايدي القناة (بشكل مباشر أو رابطها):",
        parse_mode=enums.ParseMode.MARKDOWN
    )
    try:
        channel_response = await client.listen.Message(filters.text, id=message.id, timeout=300)
        channel_id = extract_channel_id(channel_response.text)
        
        # طلب رابط الرسالة الأولى
        await client.send_message(
            message.chat.id,
            "📩 يرجى إرسال رابط الرسالة الأولى في القناة:",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        first_msg_response = await client.listen.Message(filters.text, id=message.id, timeout=300)
        first_msg_id = extract_message_id(first_msg_response.text)
        
        return channel_id, first_msg_id
        
    except asyncio.TimeoutError:
        await message.reply("🕒 انتهى الوقت المحدد للإدخال!")
        return None, None

def extract_channel_id(text):
    # استخراج ايدي القناة من الروابط أو النصوص
    if text.startswith("https://t.me/"):
        username = text.split("/")[-1]
        return resolve_channel_id(username)
    elif text.startswith("-100"):
        return int(text)
    else:
        return int(text) if text.isdigit() else None

def extract_message_id(text):
    # استخراج ايدي الرسالة من الرابط
    if "https://t.me/" in text:
        return int(text.split("/")[-1])
    return int(text) if text.isdigit() else 0

async def log_deleted_message(client, message):
    # تسجيل الرسالة المحذوفة في قناة اللوج
    try:
        log_text = f"🗑 **تم حذف رسالة مكررة**\n\n"
        log_text += f"📄 اسم الملف: `{message.document.file_name}`\n"
        log_text += f"🆔 ايدي الرسالة: `{message.id}`\n"
        log_text += f"📅 التاريخ: `{message.date}`\n"
        log_text += f"👤 المرسل: {message.from_user.mention if message.from_user else 'غير معروف'}"
        
        await client.send_message(
            CHANNEL_ID_LOG,
            log_text,
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Error logging message: {e}")

@app.on_message(filters.command("start"))
async def setup(client, message):
    # بدء عملية الإعداد
    channel_id, first_msg_id = await request_channel_info(client, message)
    
    if channel_id and first_msg_id:
        # حفظ الإعدادات
        config['SETTINGS'] = {
            'CHANNEL_ID': str(channel_id),
            'FIRST_MSG_ID': str(first_msg_id)
        }
        with open('config.ini', 'w') as f:
            config.write(f)
            
        await message.reply(
            f"✅ تم حفظ الإعدادات بنجاح!\n"
            f"القناة: `{channel_id}`\n"
            f"الرسالة الأولى: `{first_msg_id}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بدء التنظيف", callback_data="start_clean")]
            ])
        )

@app.on_callback_query(filters.regex("start_clean"))
async def start_cleaning(client, callback_query):
    try:
        # تحميل الإعدادات
        channel_id = int(config['SETTINGS']['CHANNEL_ID'])
        first_msg_id = int(config['SETTINGS']['FIRST_MSG_ID'])
        
        # بدء عملية الحذف
        await process_cleaning(client, callback_query.message, channel_id, first_msg_id)
        
    except KeyError:
        await callback_query.answer("❌ لم يتم إعداد القناة بعد!", show_alert=True)

async def process_cleaning(client, message, channel_id, first_msg_id):
    total_deleted = 0
    try:
        last_msg = (await client.get_chat_history(channel_id, limit=1))[0]
        
        progress_msg = await message.reply("⏳ جاري البدء في عملية التنظيف...")
        
        async for msg in client.get_chat_history(channel_id):
            if msg.id < first_msg_id:
                break
                
            if msg.document:
                filename = msg.document.file_name
                duplicates = []
                
                async for m in client.search_messages(channel_id, query=filename):
                    if m.id != msg.id and m.document and m.document.file_name == filename:
                        duplicates.append(m.id)
                
                if duplicates:
                    await client.delete_messages(channel_id, duplicates)
                    total_deleted += len(duplicates)
                    
                    # تسجيل الرسائل المحذوفة
                    for dup_id in duplicates:
                        dup_msg = await client.get_messages(channel_id, dup_id)
                        await log_deleted_message(client, dup_msg)
                    
                    await progress_msg.edit_text(
                        f"🚮 تم حذف {len(duplicates)} رسائل مكررة\n"
                        f"🔄 جاري متابعة العملية..."
                    )
        
        await progress_msg.edit_text(
            f"✅ اكتملت العملية!\n"
            f"إجمالي المحذوفات: {total_deleted}"
        )
        
    except FloodWait as e:
        await progress_msg.edit_text(f"⏳ يرجى الانتظار {e.value} ثانية بسبب الضغط")
        await asyncio.sleep(e.value)
        await process_cleaning(client, message, channel_id, first_msg_id)
        
    except RPCError as e:
        await message.reply(f"❌ حدث خطأ: {e}")

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
