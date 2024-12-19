from telethon.sync import TelegramClient
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from alive import keep_alive
from dotenv import load_dotenv
import configparser
import asyncio
import os

config = configparser.ConfigParser()

config.read('config.ini')

load_dotenv()

# Your API details
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
SESSION = os.getenv('SESSION')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
FIRST_MSG_ID = int(os.getenv('FIRST_MSG_ID', 0))

# Global counter for deleted messages
total_deleted_count = 0


def edit_config(progress, current_msg_id, last_msg_id, remaining_msg):
    # Read the existing config file
    config.read('config.ini')
    
    # Add a "status" section if it doesn't exist
    if "status" not in config:
        config.add_section("status")
    
    # Update the values in the "status" section
    config["status"]["progress"] = str(progress)
    config["status"]["current_msg_id"] = str(current_msg_id)
    config["status"]["last_msg_id"] = str(last_msg_id)
    config["status"]["remaining_msg"] = str(remaining_msg)
    config["status"]["total_delete_count"] = str(total_deleted_count)

    # Write the changes back to the file
    with open('config.ini', 'w') as configfile:
        config.write(configfile)



async def delete_message(client, chat, query_msg_id, duplicate_msg_ids):
    global total_deleted_count
    chunk_size = 99  # Telegram API limit
    for i in range(0, len(duplicate_msg_ids), chunk_size):
        chunk = duplicate_msg_ids[i:i + chunk_size]
        try:
            await client.delete_messages(chat, chunk)
            total_deleted_count += len(chunk)  # Update global counter
            print(f"ID {query_msg_id}: Deleted duplicate messages {chunk}")
            await asyncio.sleep(2)  # Short delay to avoid spam
        except FloodWaitError as e:
            print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"Error deleting messages {chunk}: {e}")


async def update_delete_status(current_msg_id, last_msg_id):
    if last_msg_id == 0:  # Avoid division by zero
        return
    
    progress = round((current_msg_id / last_msg_id) * 100, 1)
    global delete_status_message
    
    delete_status_message = (
        f"Deletion Progress: {progress:.2f}%\n"
        f"Processed Message ID: {current_msg_id}\n"
        f"Last Message ID to Process: {last_msg_id}\n"
        f"Remaining Messages: {last_msg_id - current_msg_id}\n"
        f"{'-' * 50}"
    )
    edit_config(progress, current_msg_id, last_msg_id, last_msg_id - current_msg_id)
    return delete_status_message


async def search_files(client, channel_id, first_msg_id):
    global total_deleted_count
    try:
        last_message = await client.get_messages(channel_id, limit=1)
        if not last_message:
            print("Error: Channel appears to be empty or inaccessible.")
            return
        
        last_msg_id = last_message[0].id

        duplicate_msg_ids = []

        for current_msg_id in range(first_msg_id, last_msg_id):
            try:
                specific_message = await client.get_messages(channel_id, ids=current_msg_id)
                if not specific_message or not specific_message.message:
                    continue

                # Extract file name from media
                query_file_name = None
                if specific_message.media and hasattr(specific_message.media, 'document'):
                    for attribute in specific_message.media.document.attributes:
                        if isinstance(attribute, DocumentAttributeFilename):
                            query_file_name = attribute.file_name
                            break

                if not query_file_name:
                    continue

                # Search for duplicates
                async for message in client.iter_messages(channel_id, search=query_file_name):
                    if (
                        message.file and 
                        hasattr(message.file, 'name') and 
                        message.file.name == query_file_name and 
                        message.id != current_msg_id
                    ):
                        duplicate_msg_ids.append(message.id)

                # Delete duplicates if found
                if duplicate_msg_ids:
                    await delete_message(client, channel_id, current_msg_id, duplicate_msg_ids)
                    duplicate_msg_ids = []  # Reset after deletion
                    await asyncio.sleep(3)  # Delay between batches

            except FloodWaitError as e:
                print(f"Rate-limited! Sleeping for {e.seconds} seconds...")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"Error processing message ID {current_msg_id}: {e}")
            
            # Update progress
            await update_delete_status(current_msg_id, last_msg_id)
            await asyncio.sleep(1)

    except Exception as e:
        print("Critical Error in search_files function:")
        print(str(e))

    return f"Total Duplicate Messages Deleted: {total_deleted_count}"

async def main():
    global total_deleted_count
    if not API_ID or not API_HASH or not SESSION or not CHANNEL_ID:
        print("Error: Missing environment variables. Check .env file.")
        return

    print("Initializing Telegram client...")
    client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

    try:
        async with client:
            await client.start()
            print("Client connected successfully.")
            print("Starting to search for duplicates...")
            try:
                await search_files(client, CHANNEL_ID, FIRST_MSG_ID)
            
            except Exception as e:
                print("Unhandled exception during search_files:")
                print(str(e))
            
            finally:
                print("Shutting down...")
                file_path = os.path.abspath("config.ini")
                await client.send_file('me', file=file_path, caption=f"Total Duplicate Messages Deleted: {total_deleted_count}")
                await client.disconnect()

    except Exception as e:
        print("Error during client initialization or execution:")
        print(str(e))


if __name__ == '__main__':
    print("Bot Started...")
    keep_alive()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🚫 Bot manually stopped. Exiting...")
    except Exception as e:
        print("Critical Error at program startup:")
        print(str(e))
