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
