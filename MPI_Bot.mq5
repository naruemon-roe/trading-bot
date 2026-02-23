//+------------------------------------------------------------------+
//| MPI_Bot.mq5                                                      |
//| Free TradingView → MT5 bridge — no MetaAPI, no extra cost        |
//|                                                                  |
//| วิธีใช้:                                                          |
//| 1. Copy ไฟล์นี้ไปที่                                             |
//|    MT5 → File > Open Data Folder > MQL5 > Experts               |
//| 2. Compile (F7)                                                  |
//| 3. ไปที่ MT5 → Tools > Options > Expert Advisors                 |
//|    ✅ Allow WebRequest for listed URL                             |
//|    เพิ่ม URL: http://<VPS_IP>:5000                               |
//| 4. ลาก EA ใส่ Chart แล้วกรอก inputs                             |
//+------------------------------------------------------------------+
#property copyright "MPI Trading Bot"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>

//── Inputs ──────────────────────────────────────────────────────────
input string   VPS_URL      = "http://YOUR_VPS_IP:5000"; // VPS URL (ห้ามลง / ท้าย)
input string   API_KEY      = "change-me";               // API_KEY เดียวกับ .env
input string   SYMBOL_TRADE = "XAUUSD";                  // Symbol ที่จะ trade
input double   LOT_TOTAL    = 0.03;                      // Lot รวม (แบ่ง 3 ออเดอร์)
input int      ATR_PERIOD   = 14;                        // ATR period
input ENUM_TIMEFRAMES ATR_TF = PERIOD_M1;               // Timeframe ของ ATR
input double   TP1_MULTI    = 1.0;                       // TP1 = entry ± ATR×1.0
input double   TP2_MULTI    = 2.0;                       // TP2 = entry ± ATR×2.0
input double   TP3_MULTI    = 3.0;                       // TP3 = entry ± ATR×3.0
input double   SL_MULTI     = 1.5;                       // SL  = entry ∓ ATR×1.5
input int      POLL_SECONDS = 3;                         // Poll ทุก N วินาที
input int      MAGIC        = 202501;                    // Magic number

//── Global variables ─────────────────────────────────────────────────
CTrade   trade;
datetime lastPoll = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MAGIC);
   Print("MPI_Bot v2.00 started | VPS=", VPS_URL,
         " | ATR period=", ATR_PERIOD, " tf=", EnumToString(ATR_TF));
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(TimeCurrent() - lastPoll < POLL_SECONDS) return;
   lastPoll = TimeCurrent();
   CheckAndExecuteSignal();
}

//+------------------------------------------------------------------+
void CheckAndExecuteSignal()
{
   // ── GET /get_signal?api_key=... ──────────────────────────────────
   string url        = VPS_URL + "/get_signal?api_key=" + API_KEY;
   char   post_data[];
   char   result_buf[];
   string result_headers;

   int code = WebRequest(
      "GET", url, "", "", 5000,
      post_data, 0, result_buf, result_headers
   );

   if(code != 200)
   {
      // ไม่ log ถ้าเป็น connection error ปกติ เพื่อไม่ spam log
      if(code != -1)
         Print("[POLL] HTTP error: ", code);
      return;
   }

   string response = CharArrayToString(result_buf, 0, WHOLE_ARRAY, CP_UTF8);

   // ไม่มี signal ใหม่
   if(StringFind(response, "\"none\"") >= 0) return;
   // ไม่ใช่ ok
   if(StringFind(response, "\"ok\"") < 0)
   {
      Print("[POLL] Unexpected response: ", response);
      return;
   }

   // ── Parse JSON fields ──────────────────────────────────────────
   string sig_id = JsonGetString(response, "id");
   string action = JsonGetString(response, "action");   // "buy" or "sell"
   double price  = JsonGetDouble(response, "price");

   if(sig_id == "" || action == "" || price <= 0)
   {
      Print("[POLL] Invalid signal data: ", response);
      return;
   }

   Print("[SIGNAL] id=", sig_id, "  action=", action, "  price=", price);

   // ── Execute trade ──────────────────────────────────────────────
   bool ok = ExecuteTrade(action, price);

   // ── Confirm signal ─────────────────────────────────────────────
   if(ok)
      ConfirmSignal(sig_id);
   else
      Print("[ERROR] Trade failed, signal NOT confirmed (will retry on next poll)");
}

//+------------------------------------------------------------------+
bool ExecuteTrade(string action, double entry_price)
{
   // คำนวณ ATR
   int atr_handle = iATR(SYMBOL_TRADE, ATR_TF, ATR_PERIOD);
   if(atr_handle == INVALID_HANDLE)
   {
      Print("[ATR] iATR() failed");
      return false;
   }

   double atr_buf[];
   ArraySetAsSeries(atr_buf, true);
   if(CopyBuffer(atr_handle, 0, 1, 1, atr_buf) < 1)
   {
      Print("[ATR] CopyBuffer failed");
      IndicatorRelease(atr_handle);
      return false;
   }
   IndicatorRelease(atr_handle);

   double atr = atr_buf[0];
   int    digits = (int)SymbolInfoInteger(SYMBOL_TRADE, SYMBOL_DIGITS);

   // คำนวณ TP1/TP2/TP3/SL
   double tp1, tp2, tp3, sl;

   if(action == "buy")
   {
      tp1 = NormalizeDouble(entry_price + atr * TP1_MULTI, digits);
      tp2 = NormalizeDouble(entry_price + atr * TP2_MULTI, digits);
      tp3 = NormalizeDouble(entry_price + atr * TP3_MULTI, digits);
      sl  = NormalizeDouble(entry_price - atr * SL_MULTI,  digits);
   }
   else // sell
   {
      tp1 = NormalizeDouble(entry_price - atr * TP1_MULTI, digits);
      tp2 = NormalizeDouble(entry_price - atr * TP2_MULTI, digits);
      tp3 = NormalizeDouble(entry_price - atr * TP3_MULTI, digits);
      sl  = NormalizeDouble(entry_price + atr * SL_MULTI,  digits);
   }

   Print("[LEVELS] ATR=", atr,
         " TP1=", tp1, " TP2=", tp2, " TP3=", tp3, " SL=", sl);

   // แบ่ง Lot : 34% / 33% / 33%
   double lots[3];
   lots[0] = NormalizeDouble(LOT_TOTAL * 0.34, 2);
   lots[1] = NormalizeDouble(LOT_TOTAL * 0.33, 2);
   lots[2] = NormalizeDouble(LOT_TOTAL * 0.33, 2);

   double tps[3]      = {tp1, tp2, tp3};
   string labels[3]   = {"MPI_TP1", "MPI_TP2", "MPI_TP3"};

   ENUM_ORDER_TYPE order_type =
      (action == "buy") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   int success_count = 0;

   for(int i = 0; i < 3; i++)
   {
      bool ok;
      if(order_type == ORDER_TYPE_BUY)
         ok = trade.Buy(lots[i], SYMBOL_TRADE, 0, sl, tps[i], labels[i]);
      else
         ok = trade.Sell(lots[i], SYMBOL_TRADE, 0, sl, tps[i], labels[i]);

      if(ok)
      {
         success_count++;
         Print("[ORDER] #", i + 1, " opened  lot=", lots[i],
               " tp=", tps[i], " sl=", sl, " label=", labels[i]);
      }
      else
      {
         Print("[ORDER] #", i + 1, " FAILED: ",
               trade.ResultRetcodeDescription(),
               " (", trade.ResultRetcode(), ")");
      }
   }

   return success_count > 0;
}

//+------------------------------------------------------------------+
void ConfirmSignal(string sig_id)
{
   string url  = VPS_URL + "/confirm_signal";
   string body = "{\"api_key\":\"" + API_KEY + "\",\"id\":\"" + sig_id + "\"}";
   string req_headers = "Content-Type: application/json\r\n";

   char post_data[];
   char result_buf[];
   string result_headers;

   // StringToCharArray ไม่ใส่ null terminator
   int body_len = StringLen(body);
   ArrayResize(post_data, body_len);
   StringToCharArray(body, post_data, 0, body_len, CP_UTF8);

   int code = WebRequest(
      "POST", url, req_headers, "", 5000,
      post_data, body_len, result_buf, result_headers
   );

   if(code == 200)
      Print("[CONFIRM] Signal confirmed: ", sig_id);
   else
      Print("[CONFIRM] Failed: HTTP ", code,
            "  body=", CharArrayToString(result_buf, 0, WHOLE_ARRAY, CP_UTF8));
}

//+------------------------------------------------------------------+
//| JSON helpers (ไม่ต้องใช้ library เพิ่ม)                         |
//+------------------------------------------------------------------+

string JsonGetString(string json, string key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double JsonGetDouble(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0;
   start += StringLen(search);
   string val = "";
   for(int i = start; i < StringLen(json); i++)
   {
      ushort c = StringGetCharacter(json, i);
      if(c == ',' || c == '}' || c == ' ' || c == '\r' || c == '\n') break;
      val += ShortToString(c);
   }
   return StringToDouble(val);
}
//+------------------------------------------------------------------+
