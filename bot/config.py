import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "userbot")

TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
TARGET_SENDER_ID = int(os.getenv("TARGET_SENDER_ID"))