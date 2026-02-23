"""
ATR Calculator
──────────────
ดึง ATR จาก MT5 ผ่าน MetaAPI แล้วคำนวณ Entry / TP1 / TP2 / TP3 / SL
"""

import logging
from config import Config

log = logging.getLogger(__name__)


class ATRCalculator:

    def __init__(self, account):
        """
        account : MetaAPI account object
                  (รับมาจาก MT5Handler.connect())
        """
        self.account = account

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    async def get_atr(self, symbol: str, period: int | None = None) -> float:
        """
        ดึง Candles จาก MetaAPI แล้วคำนวณ ATR

        คืนค่า Fallback ถ้าดึงไม่ได้
        """
        period = period or Config.ATR_PERIOD
        try:
            candles = await self.account.get_historical_candles(
                symbol     = symbol,
                timeframe  = Config.TIMEFRAME,
                start_time = None,
                limit      = period + 1,
            )

            if not candles or len(candles) < 2:
                raise ValueError(f"need >{period} candles, got {len(candles or [])}")

            atr = self._calc_atr(candles, period)
            log.info("[ATR] %s ATR(%s) = %s", symbol, period, atr)
            return atr

        except Exception as exc:
            fallback = Config.ATR_FALLBACK.get(symbol, 1.0)
            log.warning("[ATR] fallback %s → %s  |  reason: %s", symbol, fallback, exc)
            return fallback

    def calculate_levels(
        self,
        entry:  float,
        action: str,
        atr:    float,
    ) -> dict:
        """
        คำนวณ TP1 / TP2 / TP3 / SL จาก ATR Multipliers ใน config

        action : "buy" | "sell"
        คืน   : {"entry", "tp1", "tp2", "tp3", "sl"}
        """
        d = atr  # shorthand

        if action == "buy":
            levels = {
                "entry": entry,
                "tp1":   self._r(entry + d * Config.TP1_MULTI),
                "tp2":   self._r(entry + d * Config.TP2_MULTI),
                "tp3":   self._r(entry + d * Config.TP3_MULTI),
                "sl":    self._r(entry - d * Config.SL_MULTI),
            }
        else:  # sell
            levels = {
                "entry": entry,
                "tp1":   self._r(entry - d * Config.TP1_MULTI),
                "tp2":   self._r(entry - d * Config.TP2_MULTI),
                "tp3":   self._r(entry - d * Config.TP3_MULTI),
                "sl":    self._r(entry + d * Config.SL_MULTI),
            }

        log.info("[LEVELS] %s %s", action.upper(), levels)
        return levels

    # ──────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _r(value: float, decimals: int = 3) -> float:
        return round(value, decimals)

    @staticmethod
    def _calc_atr(candles: list, period: int) -> float:
        """Wilder's ATR (simple average version)"""
        true_ranges = []
        for i in range(1, len(candles)):
            h  = candles[i]["high"]
            l  = candles[i]["low"]
            pc = candles[i - 1]["close"]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            true_ranges.append(tr)

        window = true_ranges[-period:]
        return round(sum(window) / len(window), 3)
