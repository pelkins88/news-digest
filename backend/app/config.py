import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DB_PATH = BACKEND_DIR / "data" / "news.db"
FEEDS_PATH = Path(__file__).resolve().parent / "feeds.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
