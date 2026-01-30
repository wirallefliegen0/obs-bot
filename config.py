import os
from dotenv import load_dotenv

load_dotenv()

OBS_USERNAME = os.getenv("OBS_USERNAME", "")
OBS_PASSWORD = os.getenv("OBS_PASSWORD", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))

OBS_BASE_URL = "https://obs.btu.edu.tr"
OBS_LOGIN_URL = f"{OBS_BASE_URL}/oibs/std/login.aspx"
OBS_GRADES_URL = f"{OBS_BASE_URL}/oibs/std/start.aspx"

CACHE_FILE = "grades_cache.json"


def validate_config():
    
    missing = []
    
    if not OBS_USERNAME:
        missing.append("OBS_USERNAME")
    if not OBS_PASSWORD:
        missing.append("OBS_PASSWORD")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return True
