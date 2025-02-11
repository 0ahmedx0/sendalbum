from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import FloodWait, RPCError
import configparser
import os
import asyncio
from enum import Enum

# تحميل المتغيرات من ملف .env
from dotenv import load_dotenv
load_dotenv()

# إعدادات ثابتة
CHANNEL_ID_LOG = -100123456789  # ضع هنا إيدي قناة اللوج
config = configparser.ConfigParser()

# حالات المستخدم
class UserState(Enum):
    IDLE = 0
    AWAITING_CHANNEL = 1
    AWAITING_FIRST_MSG = 2

user_states = {}

app = Client(
    "bot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN")
)

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

def extract_channel_id(text: str) -> int:
    """استخراج إيدي القناة من الرابط أو النص"""
    if text.startswith("https://t.me/"):
        username = text.split("/")[-1]
        try:
            return app.get_chat(username).id
        except Exception:
            return None
    return int(text) if text.lstrip('-').isdigit() else None

def extract_message_id(text: str) -> int:
    """استخراج إيدي الرسالة من الرابط"""
    if "https://t.me/" in text:
        return int(text.split("/")[-1])
    return int(text) if text.isdigit() else 0

async def log_deletion(message: Message):
    """تسجيل الرسالة المحذوفة في قناة اللوج"""
    try:
        log_text = (
            f"🗑 **تم حذف رسالة مكررة**\n\n"
            f"📄 اسم الملف: `{message.document.file_name}`\n"
            f"🆔 ايدي الرسالة: `{message.id}`\n"
            f"📅 التاريخ: `{message.date}`"
        )
        await app.send_message(CHANNEL_ID_LOG, log_text)
    except Exception as e:
        print(f"فشل في التسجيل: {e}")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """بدء العملية"""
    user_id = message.from_user.id
    user_states[user_id] = UserState.AWAITING_CHANNEL
    await message.reply(
        "مرحبا! 👋\n"
        "أرسل لي إيدي القناة أو رابطها:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("إلغاء العملية", callback_data="cancel")]
        ])
    )

@app.on_message(filters.private & ~filters.command("start"))
async def handle_input(client: Client, message: Message):
    """معالجة إدخال المستخدم"""
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state:
        return

    if state == UserState.AWAITING_CHANNEL:
        # معالجة إدخال القناة
        channel_id = extract_channel_id(message.text)
        print(f"تم استخراج معرف القناة: {channel_id}") # إضافة هذا السطر
        print(f"تم استخراج معرف القناة: {channel_id}")

        try:
            chat = await client.get_chat(channel_id)    
            print(f"✅ تم الوصول للقناة بنجاح: {chat.title} (ID: {chat.id})")
                except Exception as e:
            print(f"❌ فشل في الوصول للقناة: {e}")
                return await message.reply(f"❌ لا يمكن الوصول إلى القناة! تأكد أن البوت عضو فيها.\nالخطأ: {str(e)}")

        if not channel_id:
            return await message.reply("❌ الرابط غير صحيح، حاول مرة أخرى!")

        try:
            # التحقق من صلاحيات البوت
            chat = await client.get_chat(channel_id)
            if not chat.permissions.can_delete_messages:
                return await message.reply("⚠️ البوت ليس لديه صلاحية الحذف في هذه القناة!")
        except Exception as e:
            return await message.reply(f"❌ خطأ في الوصول إلى القناة: {str(e)}")

        user_states[user_id] = UserState.AWAITING_FIRST_MSG
        config['SETTINGS']['CHANNEL_ID'] = str(channel_id)
        await message.reply("📩 أرسل الآن رابط الرسالة الأولى:")

    elif state == UserState.AWAITING_FIRST_MSG:
        # معالجة إدخال الرسالة الأولى
        first_msg_id = extract_message_id(message.text)
        print(f"تم استخراج معرف الرسالة الأولى: {first_msg_id}") # إضافة هذا السطر
        config['SETTINGS']['FIRST_MSG_ID'] = str(first_msg_id)

        with open('config.ini', 'w') as f:
            config.write(f)

        del user_states[user_id]
        await message.reply(
            "✅ تم حفظ الإعدادات بنجاح!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بدء التنظيف الآن ▶️", callback_data="start_clean")]
            ])
        )
@app.on_callback_query(filters.regex("start_clean"))
async def start_cleaning(client: Client, callback_query):
    """بدء عملية التنظيف"""
    try:
        channel_id = int(config['SETTINGS']['CHANNEL_ID'])
        first_msg_id = int(config['SETTINGS']['FIRST_MSG_ID'])
        
        progress_msg = await callback_query.message.reply("⚙️ جاري بدء العملية...")
        
        async for msg in client.get_chat_history(channel_id):
            if msg.id < first_msg_id:
                break
            
            if msg.document:
                duplicates = []
                async for m in client.search_messages(channel_id, query=msg.document.file_name):
                    if m.id == msg.id:
                        continue
                    if m.document.file_name == msg.document.file_name:
                        if config.getboolean('SETTINGS', 'CHECK_SIZE', fallback=True):
                            if m.document.file_size != msg.document.file_size:
                                continue
                        duplicates.append(m.id)
                
                if duplicates:
                    await client.delete_messages(channel_id, duplicates)
                    for dup_id in duplicates:
                        dup_msg = await client.get_messages(channel_id, dup_id)
                        await log_deletion(dup_msg)
                    
                    await progress_msg.edit_text(
                        f"♻️ تم معالجة {msg.id}:\n"
                        f"تم حذف {len(duplicates)} نسخة مكررة"
                    )
        
        await progress_msg.edit_text("✅ اكتملت العملية بنجاح!")
    
    except FloodWait as e:
        await progress_msg.edit_text(f"⏳ يرجى الانتظار {e.value} ثانية...")
        await asyncio.sleep(e.value)
        await start_cleaning(client, callback_query)
    except Exception as e:
        await callback_query.message.reply(f"❌ فشلت العملية: {str(e)}")
    finally:
        await callback_query.answer()

@app.on_callback_query(filters.regex("cancel"))
async def cancel_handler(client: Client, callback_query):
    """إلغاء العملية"""
    user_id = callback_query.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    await callback_query.message.edit_text("❌ تم إلغاء العملية")
    await callback_query.answer()

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
