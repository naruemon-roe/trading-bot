import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    # API_KEY ใช้ validate ทั้ง TradingView webhook และ MT5 EA polling
    API_KEY = os.getenv("API_KEY", "change-me")

    # ── Trading default ───────────────────────────────────────────────────────
    # Symbol default ถ้า TradingView ไม่ส่งมา
    SYMBOL = os.getenv("SYMBOL", "XAUUSD")

    # ── Discord ───────────────────────────────────────────────────────────────
    # ใส่ Discord Webhook URL เพื่อรับแจ้งเตือน (ถ้าไม่ต้องการให้เว้นว่าง)
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
