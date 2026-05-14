import os
from dotenv import load_dotenv

load_dotenv()


class Config:

    # ==================================================
    # SECURITY
    # ==================================================
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "gigamas-secret-key"
    )

    # ==================================================
    # DATABASE
    # ==================================================
    database_url = os.getenv("DATABASE_URL")

    # fallback lokal
    if not database_url:
        database_url = (
            "postgresql://postgres:admin777@localhost:5434/gigamas"
        )

    # fix render/heroku postgres://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    SQLALCHEMY_DATABASE_URI = database_url

    # ==================================================
    # SQLALCHEMY
    # ==================================================
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280
    }

    # ==================================================
    # WHATSAPP API
    # ==================================================
    WHATSAPP_ACCESS_TOKEN = os.getenv(
        "WHATSAPP_ACCESS_TOKEN"
    )

    WHATSAPP_PHONE_NUMBER_ID = os.getenv(
        "WHATSAPP_PHONE_NUMBER_ID"
    )

    WHATSAPP_API_VERSION = os.getenv(
        "WHATSAPP_API_VERSION",
        "v20.0"
    )

    # ==================================================
    # ALERT SYSTEM
    # ==================================================
    BATAS_BARANG_KELUAR_BESAR = int(
        os.getenv(
            "BATAS_BARANG_KELUAR_BESAR",
            100
        )
    )