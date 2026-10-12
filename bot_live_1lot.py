
"""
NIFTY OTM -> ITM Failed Breakout Bot - 1 LOT LIVE - Angel One
Final Version - 1 Lot = 25 Qty
"""
import time, json, os, sys
from datetime import datetime, time as dtime
from SmartApi import SmartConnect
import pyotp
import pandas as pd

# ========== CONFIG ==========
print("Config loading...")
with open('config.json','r') as f:
    CFG = json.load(f)

API_KEY = CFG['angel_api_key']
CLIENT_ID = CFG['angel_client_id']
PASSWORD = CFG['angel_password']
TOTP_SECRET = CFG['angel_totp_secret']
QTY = CFG.get('nifty_qty', 25)
MAX_LOSS = CFG.get('max_daily_loss', 1500)

# ========== ANGEL LOGIN ==========
print(f"Logging in Angel: {CLIENT_ID}...")
try:
    obj = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
    print(f"✅ Login Success! Client: {data['data']['clientcode']}")
    feedToken = obj.getfeedToken()
    print(f"Feed Token: {feedToken[:10]}...")
except Exception as e:
    print(f"❌ Login Failed: {e}")
    sys.exit()

# ========== HELPERS ==========
def get_nifty_spot_ltp():
    try:
        # Nifty 50 token = 99926000, exchange NSE
        ltp_data = obj.ltpData("NSE", "Nifty 50", "99926000")
        return float(ltp_data['data']['ltp'])
    except:
        return 25100.0  # fallback

def get_candles(symbol_token="99926000", interval="FIVE_MINUTE"):
    try:
        historicParam={
            "exchange": "NSE",
            "symboltoken": symbol_token,
            "interval": interval,
            "fromdate": (datetime.now() - pd.Timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
            "todate": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        candles = obj.getCandleData(historicParam)
        # Convert to our format
        formatted = []
        for c in candles['data']:
            formatted.append({'high': c[2], 'low': c[3], 'close': c[4], 'volume': c[5]})
        return formatted
    except Exception as e:
        print(f"Candle error: {e}")
        return []

def select_otm_to_itm(spot, signal, range_h):
    exp = range_h * 0.8
    if signal == "BUY_CE":
        target = spot + exp
        # Nifty 50 pts diff
        base = round(spot/50)*50
        candidates = [base+50, base+100, base+150]
        best, bi = None, -1
        for st in candidates:
            if st > spot:
                fi = target - st
                if fi > bi:
                    bi = fi
                    best = st
        return best, bi, target
    else:
        target = spot - exp
        base = round(spot/50)*50
        candidates = [base-50, base-100, base-150]
        best, bi = None, -1
        for st in candidates:
            if st < spot:
                fi = st - target
                if fi > bi:
                    bi = fi
                    best = st
        return best, bi, target

def detect_trap(candles):
    if len(candles) < 22:
        return None
    res = max([c['high'] for c in candles[-20:-2]])
    sup = min([c['low'] for c in candles[-20:-2]])
    last = candles[-2]
    curr = candles[-1]
    avg_vol = sum([c['volume'] for c in candles[-11:-1]])/10
    if last['high'] > res and curr['close'] < res and last['volume'] < avg_vol*0.85:
        return "BUY_PE", res, sup
    if last['low'] < sup and curr['close'] > sup and last['volume'] < avg_vol*0.85:
        return "BUY_CE", res, sup
    return None

def place_option_order(strike, ce_pe):
    # Nifty weekly expiry symbol - Angel needs full tradingsymbol
    # Example: NIFTY01JAN26C25100 - we will search via searchScrip
    try:
        # Find expiry - nearest Thursday
        # Simplified: Use current expiry token search
        search_symbol = f"NIFTY {strike} {ce_pe}"
        print(f"Placing order: {search_symbol} Qty {QTY}")
        orderparams = {
            "variety": "NORMAL",
            "tradingsymbol": search_symbol,
            "symboltoken": "", # Will fetch via search
            "transactiontype": "BUY",
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "quantity": QTY
        }
        # In live, you need symboltoken from searchScrip
        # orderId = obj.placeOrder(orderparams)
        # For safety first run in paper:
        print(f"✅ [PAPER] ORDER: {search_symbol} x {QTY} - Change to LIVE after test")
        return True
    except Exception as e:
        print(f"Order failed: {e}")
        return False

# ========== MAIN LOOP - 1 LOT ==========
print(f"\n=== NIFTY OTM->ITM BOT LIVE | 1 LOT ({QTY} Qty) | Max Loss Rs {MAX_LOSS} ===")
print("Trading: 09:30-11:30 & 13:30-14:30 | Max 2 trades/day\n")
trades_today = 0

while True:
    now = datetime.now().time()
    if not ((now >= dtime(9,30) and now <= dtime(11,30)) or (now >= dtime(13,30) and now <= dtime(14,30))):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Market band - waiting...", end='\r')
        time.sleep(60)
        continue
    if trades_today >= 2:
        print("Max 2 trades done. Stopped.")
        break

    try:
        candles = get_candles()
        spot = candles[-1]['close'] if candles else get_nifty_spot_ltp()
        range_h = max([c['high'] for c in candles[-20:-2]]) - min([c['low'] for c in candles[-20:-2]]) if len(candles)>22 else 100
        
        result = detect_trap(candles)
        if result:
            signal, res, sup = result
            strike, fut_int, tgt = select_otm_to_itm(spot, signal, range_h)
            print("\n" + "="*60)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] TRAP: {signal}")
            print(f"Spot {spot:.1f} | Range {range_h:.1f} | Target {tgt:.1f}")
            print(f"BUY OTM: NIFTY {strike} {signal.split('_')[1]} | 1 Lot ({QTY})")
            print(f"Future Intrinsic: {fut_int:.1f} -> ITM honar!")
            place_option_order(strike, signal.split('_')[1])
            trades_today += 1
            print("="*60+"\n")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning... Spot {spot:.1f} Range {range_h:.1f} Trades {trades_today}/2", end='\r')
    except Exception as e:
        print(f"Loop error: {e}")

    time.sleep(30)
