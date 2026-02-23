"""
Trading Bot – Signal Server  (v2 – Free, No MetaAPI)
─────────────────────────────────────────────────────
Architecture:
  TradingView → POST /webhook  → เก็บ signal ใน SQLite
  MT5 EA      → GET  /get_signal  → อ่าน signal ที่รอ
  MT5 EA      → POST /confirm_signal → confirm หลัง trade executed

ไม่ต้องใช้ MetaAPI หรือ MetaTrader5 package เลย
MT5 EA บน PC ของคุณทำ trade เองทั้งหมด
"""

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

import requests

from flask import Flask, request, jsonify

from config import Config


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


# ── App ────────────────────────────────────────────────────────────────────────

app    = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "signals.db")


# ── SQLite Setup ───────────────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id        TEXT PRIMARY KEY,
                action    TEXT NOT NULL,
                symbol    TEXT NOT NULL,
                price     REAL NOT NULL,
                timeframe TEXT NOT NULL DEFAULT '',
                status    TEXT NOT NULL DEFAULT 'pending',
                created   TEXT NOT NULL,
                confirmed TEXT
            )
        """)
        # migrate existing DB — add timeframe column if missing
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN timeframe TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()

init_db()


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Discord Notification ──────────────────────────────────────────────────────

def send_discord(action: str, symbol: str, price: float, timeframe: str, signal_id: str) -> None:
    """ส่ง embed notification ไป Discord Webhook"""
    url = Config.DISCORD_WEBHOOK_URL
    if not url:
        return

    is_buy = action.lower() == "buy"
    color  = 0x2ECC71 if is_buy else 0xE74C3C  # green | red
    emoji  = "\U0001f7e2" if is_buy else "\U0001f534"

    payload = {
        "embeds": [{
            "title":  f"{emoji} {action.upper()} Signal | {symbol}",
            "color":  color,
            "fields": [
                {"name": "Symbol",    "value": symbol,             "inline": True},
                {"name": "Action",    "value": action.upper(),     "inline": True},
                {"name": "Price",     "value": str(price),         "inline": True},
                {"name": "Timeframe", "value": timeframe or "N/A", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer":    {"text": f"Signal ID: {signal_id}"},
        }]
    }

    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code not in (200, 204):
            log.warning("[DISCORD] HTTP %s", resp.status_code)
    except Exception as exc:
        log.warning("[DISCORD] failed: %s", exc)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check สำหรับ Uptime Monitor"""
    return jsonify({
        "status": "ok",
        "utc":    datetime.now(timezone.utc).isoformat(),
        "symbol": Config.SYMBOL,
    })


@app.post("/V2/webhook")
def webhook():
    """
    รับ JSON Payload จาก TradingView Alert

    Expected body:
    {
        "api_key": "...",
        "action":  "buy" | "sell",
        "symbol":  "XAUUSD",   (optional, fallback to config)
        "price":   2650.0      (float หรือ string ก็ได้)
    }
    """
    data = request.get_json(silent=True) or {}
    log.info("[WEBHOOK] %s", data)

    # Auth
    if data.get("api_key") != Config.API_KEY:
        log.warning("[WEBHOOK] Unauthorized")
        return jsonify({"error": "Unauthorized"}), 401

    action    = str(data.get("action", "")).strip().lower()
    symbol    = str(data.get("symbol", Config.SYMBOL)).strip().upper()
    timeframe = str(data.get("timeframe", "")).strip()

    try:
        price = float(data["price"])
        assert price > 0
    except (KeyError, ValueError, AssertionError):
        return jsonify({"error": "price ต้องเป็นตัวเลขที่มากกว่า 0"}), 400

    if action not in ("buy", "sell"):
        return jsonify({"error": f"action ต้องเป็น buy หรือ sell ไม่ใช่ '{action}'"}), 400

    # Store signal
    signal_id = str(uuid.uuid4())
    now       = datetime.now(timezone.utc).isoformat()

    with _db() as conn:
        conn.execute(
            "INSERT INTO signals (id, action, symbol, price, timeframe, status, created) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (signal_id, action, symbol, price, timeframe, now),
        )
        conn.commit()

    log.info("[STORED] id=%s  %s %s @ %s  tf=%s", signal_id, action, symbol, price, timeframe)
    send_discord(action, symbol, price, timeframe, signal_id)
    return jsonify({"status": "stored", "signal_id": signal_id})


@app.get("/get_signal")
def get_signal():
    """
    MT5 EA polls นี้ทุก N วินาที

    ต้องส่ง ?api_key=... ใน query string
    คืน oldest pending signal หรือ {"status":"none"} ถ้าไม่มี
    """
    if request.args.get("api_key") != Config.API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE status = 'pending' ORDER BY created ASC LIMIT 1"
        ).fetchone()

    if row is None:
        return jsonify({"status": "none"})

    return jsonify({
        "status":    "ok",
        "id":        row["id"],
        "action":    row["action"],
        "symbol":    row["symbol"],
        "price":     row["price"],
        "timeframe": row["timeframe"],
        "created":   row["created"],
    })


@app.post("/confirm_signal")
def confirm_signal():
    """
    MT5 EA เรียกหลังจาก trade executed เรียบร้อย

    Body: { "api_key": "...", "id": "<signal-uuid>" }
    """
    data = request.get_json(silent=True) or {}

    if data.get("api_key") != Config.API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    signal_id = data.get("id")
    if not signal_id:
        return jsonify({"error": "missing id"}), 400

    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        affected = conn.execute(
            "UPDATE signals SET status='confirmed', confirmed=? WHERE id=? AND status='pending'",
            (now, signal_id),
        ).rowcount
        conn.commit()

    if affected == 0:
        return jsonify({"error": "signal not found or already confirmed"}), 404

    log.info("[CONFIRMED] id=%s", signal_id)
    return jsonify({"status": "confirmed"})


@app.get("/signals")
def list_signals():
    """Debug endpoint – ดู signals 50 รายการล่าสุด (ต้องมี api_key)"""
    if request.args.get("api_key") != Config.API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY created DESC LIMIT 50"
        ).fetchall()

    return jsonify([dict(r) for r in rows])


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("Starting Signal Server on port %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
