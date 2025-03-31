import asyncio
from pyrogram import Client
import os

# إعدادات الاتصال
API_ID = int(os.getenv("API_ID", "YOUR_API_ID"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
SESSION = os.getenv("SESSION", "YOUR_SESSION_STRING")

# إعدادات القنوات
SOURCE_CHANNEL = "-1002236961858"  # معرف القناة المقيدة (بدون username)
DEST_CHANNEL = "@your_channel_username"  # معرف قناتك (يُفضل username أو ID إذا خاصة)

# المدى الزمني للرسائل
FIRST_MSG_ID = 1601
LAST_MSG_ID = 1650

async def main():
    async with Client("forwarder", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as app:
        print("🚀 بدأ تحويل الرسائل...")
        for msg_id in range(FIRST_MSG_ID, LAST_MSG_ID + 1):
            try:
                await app.forward_messages(
                    chat_id=DEST_CHANNEL,
                    from_chat_id=SOURCE_CHANNEL,
                    message_ids=msg_id
                )
                print(f"✅ تم تحويل الرسالة {msg_id}")
                await asyncio.sleep(1)  # لتجنب FloodWait
            except Exception as e:
                print(f"❌ فشل تحويل الرسالة {msg_id}: {e}")
                await asyncio.sleep(2)

        print("✅ تم تحويل جميع الرسائل المطلوبة!")

if __name__ == "__main__":
    asyncio.run(main())
