"""
MT5 Handler (via MetaAPI Cloud)
────────────────────────────────
เชื่อมต่อ MT5 จาก Linux โดยไม่ต้องติดตั้ง MT5 บนเครื่อง
เปิด Order แบบ Split 3 Positions (TP1 / TP2 / TP3)
"""

import logging
from metaapi_cloud_sdk import MetaApi
from config import Config

log = logging.getLogger(__name__)


class MT5Handler:

    def __init__(self):
        self._api:     MetaApi | None = None
        self._account                 = None

    # ──────────────────────────────────────────
    # Connection
    # ──────────────────────────────────────────

    async def connect(self):
        """
        เชื่อมต่อ MetaAPI ครั้งเดียว แล้ว Cache ไว้
        ถ้าเชื่อมอยู่แล้วคืน account เดิมเลย
        """
        if self._account is not None:
            log.debug("[MT5] เชื่อมต่ออยู่แล้ว")
            return self._account

        log.info("[MT5] กำลังเชื่อมต่อ MetaAPI...")
        self._api     = MetaApi(Config.META_API_TOKEN)
        self._account = await self._api.metatrader_account_api.get_account(
            Config.META_ACCOUNT_ID
        )

        if self._account.state not in ("DEPLOYING", "DEPLOYED"):
            await self._account.deploy()

        await self._account.wait_connected()
        log.info("[MT5] เชื่อมต่อสำเร็จ!")
        return self._account

    async def disconnect(self):
        """ตัดการเชื่อมต่อ MetaAPI"""
        if self._api:
            await self._api.close()
            self._api     = None
            self._account = None
            log.info("[MT5] ตัดการเชื่อมต่อแล้ว")

    # ──────────────────────────────────────────
    # Orders
    # ──────────────────────────────────────────

    async def place_split_orders(
        self,
        symbol:    str,
        action:    str,
        levels:    dict,
        lot_size:  float | None = None,
        lot_split: list | None  = None,
    ) -> list[dict]:
        """
        เปิด 3 Orders แบ่ง Lot ตาม TP1 / TP2 / TP3

        Parameters
        ──────────
        symbol    : เช่น "XAUUSD"
        action    : "buy" | "sell"
        levels    : {"entry", "tp1", "tp2", "tp3", "sl"}
        lot_size  : รวม Lot ทั้งหมด  (ใช้ Config ถ้าไม่ระบุ)
        lot_split : สัดส่วนแต่ละ Position (ใช้ Config ถ้าไม่ระบุ)

        คืน List ของผลลัพธ์แต่ละ Order
        """
        lot_size  = lot_size  or Config.LOT_SIZE
        lot_split = lot_split or Config.LOT_SPLIT
        sl        = levels["sl"]
        tps       = [levels["tp1"], levels["tp2"], levels["tp3"]]
        results   = []

        # เปิด Streaming Connection ครั้งเดียว
        conn = self._account.get_streaming_connection()
        await conn.connect()
        await conn.wait_synchronized()

        try:
            for i, (tp, ratio) in enumerate(zip(tps, lot_split)):
                lot   = max(round(lot_size * ratio, 2), 0.01)
                label = f"MPI_TP{i + 1}"

                try:
                    res = await self._market_order(
                        conn    = conn,
                        symbol  = symbol,
                        action  = action,
                        lot     = lot,
                        tp      = tp,
                        sl      = sl,
                        comment = label,
                    )
                    log.info("[ORDER ✅] %s %s %s %.2f  TP=%.3f  SL=%.3f",
                             label, action.upper(), symbol, lot, tp, sl)
                    results.append({
                        "position": i + 1,
                        "label":    label,
                        "lot":      lot,
                        "tp":       tp,
                        "sl":       sl,
                        "success":  True,
                        "order_id": res.get("orderId"),
                    })

                except Exception as exc:
                    log.error("[ORDER ❌] %s failed: %s", label, exc)
                    results.append({
                        "position": i + 1,
                        "label":    label,
                        "lot":      lot,
                        "tp":       tp,
                        "sl":       sl,
                        "success":  False,
                        "error":    str(exc),
                    })

        finally:
            await conn.close()

        return results

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    @staticmethod
    async def _market_order(
        conn,
        symbol:  str,
        action:  str,
        lot:     float,
        tp:      float,
        sl:      float,
        comment: str,
    ) -> dict:
        order_type = "ORDER_TYPE_BUY" if action == "buy" else "ORDER_TYPE_SELL"
        return await conn.create_market_order(
            symbol      = symbol,
            volume      = lot,
            order_type  = order_type,
            stop_loss   = sl,
            take_profit = tp,
            options     = {"comment": comment},
        )
