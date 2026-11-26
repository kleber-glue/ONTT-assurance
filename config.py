import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
    UPLOAD_FOLDER = Path(os.getenv("UPLOAD_FOLDER", BASE_DIR / "uploads"))
    SQL_FOLDER = Path(os.getenv("SQL_FOLDER", BASE_DIR / "generated"))
    DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "instance" / "app.db"))
    ALLOWED_EXTENSIONS = {"xlsx"}
