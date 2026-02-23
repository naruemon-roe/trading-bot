import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Security ──────────────────────────────
    API_KEY = os.getenv("API_KEY", "change-me")

    # ── MetaAPI Cloud ─────────────────────────
    META_API_TOKEN  = os.getenv("META_API_TOKEN")
    META_ACCOUNT_ID = os.getenv("META_ACCOUNT_ID")

    # ── Trading ───────────────────────────────
    SYMBOL     = os.getenv("SYMBOL", "XAUUSD")
    LOT_SIZE   = float(os.getenv("LOT_SIZE", "0.01"))
    ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
    TIMEFRAME  = os.getenv("TIMEFRAME", "1m")

    # ── ATR Multipliers ───────────────────────
    # TP = entry ± (ATR × multiplier)
    # SL = entry ∓ (ATR × multiplier)
    TP1_MULTI = float(os.getenv("TP1_MULTI", "1.0"))
    TP2_MULTI = float(os.getenv("TP2_MULTI", "2.0"))
    TP3_MULTI = float(os.getenv("TP3_MULTI", "3.0"))
    SL_MULTI  = float(os.getenv("SL_MULTI",  "1.5"))

    # ── Lot split per position [TP1, TP2, TP3] ─
    # ต้องรวมกันได้ = 1.0
    LOT_SPLIT = [0.34, 0.33, 0.33]

    # ── Fallback ATR when API call fails ──────
    ATR_FALLBACK: dict = {
        "XAUUSD": 5.0,
        "EURUSD": 0.0010,
        "GBPUSD": 0.0015,
        "USDJPY": 0.15,
        "BTCUSD": 200.0,
    }
