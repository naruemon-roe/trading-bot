"""
Trading Bot – Main App
──────────────────────
รับ TradingView Webhook → คำนวณ ATR TP/SL → Execute บน MT5 ผ่าน MetaAPI
ทำงานทั้งหมดบน Linux VPS ไม่ต้องมี Windows PC
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify

from config import Config
from mt5_handler import MT5Handler
from atr_calculator import ATRCalculator


# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── App & Global Handler ──────────────────────────────────────────────────────

app = Flask(__name__)
mt5 = MT5Handler()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check สำหรับ Uptime Monitor"""
    return jsonify({
        "status": "ok",
        "utc":    datetime.now(timezone.utc).isoformat(),
        "symbol": Config.SYMBOL,
        "lot":    Config.LOT_SIZE,
    })


@app.post("/webhook")
def webhook():
    """
    รับ JSON Payload จาก TradingView Alert

    Expected body:
    {
        "api_key": "...",
        "action":  "buy" | "sell",
        "symbol":  "XAUUSD",       (optional, fallback to config)
        "price":   2650.0          (float หรือ string ก็ได้)
    }
    """
    data = request.get_json(silent=True) or {}
    log.info("[WEBHOOK] %s", data)

    # ── Auth ──────────────────────────────────────────────────────────────────
    if data.get("api_key") != Config.API_KEY:
        log.warning("[WEBHOOK] Unauthorized attempt")
        return jsonify({"error": "Unauthorized"}), 401

    # ── Parse & Validate ──────────────────────────────────────────────────────
    action = str(data.get("action", "")).strip().lower()
    symbol = str(data.get("symbol", Config.SYMBOL)).strip().upper()

    try:
        price = float(data["price"])
        assert price > 0
    except (KeyError, ValueError, AssertionError):
        return jsonify({"error": "price ต้องเป็นตัวเลขที่มากกว่า 0"}), 400

    if action not in ("buy", "sell"):
        return jsonify({"error": f"action ต้องเป็น buy หรือ sell ไม่ใช่ '{action}'"}), 400

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        result = asyncio.run(_execute(action, symbol, price))
        return jsonify({"status": "success", "result": result})
    except Exception as exc:
        log.error("[EXECUTE ERROR] %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ── Core Trade Logic ──────────────────────────────────────────────────────────

async def _execute(action: str, symbol: str, price: float) -> dict:
    """
    1. Connect MT5
    2. คำนวณ ATR จาก Candle History
    3. คำนวณ TP1 / TP2 / TP3 / SL
    4. เปิด 3 Orders แบ่ง Lot
    """

    # 1. Connect
    account = await mt5.connect()

    # 2. ATR
    calc = ATRCalculator(account)
    atr  = await calc.get_atr(symbol)

    # 3. Levels
    levels = calc.calculate_levels(
        entry  = price,
        action = action,
        atr    = atr,
    )

    # 4. Orders
    orders = await mt5.place_split_orders(
        symbol = symbol,
        action = action,
        levels = levels,
    )

    success_count = sum(1 for o in orders if o.get("success"))
    log.info("[DONE] %s/%s orders สำเร็จ  levels=%s", success_count, len(orders), levels)

    return {
        "symbol":  symbol,
        "action":  action,
        "price":   price,
        "atr":     atr,
        "levels":  levels,
        "orders":  orders,
        "success": success_count,
    }


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("Starting Trading Bot on port %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
