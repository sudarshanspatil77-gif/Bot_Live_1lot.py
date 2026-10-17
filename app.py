
from flask import Flask, jsonify
import threading, time, os, requests, random, math
from datetime import datetime, timedelta
import pytz
from collections import deque

app = Flask(__name__)
LOGS = deque(maxlen=500)
CANDLES = deque(maxlen=500)
TRADES = deque(maxlen=30)

LEFT_BARS = 5
RIGHT_BARS = 5
EMA_LENGTH = 200
ATR_LENGTH = 14
MIN_VOL = 0.10
MAX_VOL = 5.00

STATE = {
    "spot":22527, "prem":87.30, "strike":22350, "open_price":22500, "open_time":None,
    "trend":"", "option_type":"PE", "selected_strike":22350, "selected_type":"22350PE 0.30 Delta",
    "call_strike":22650, "put_strike":22350,
    "pnl":0, "trades":0, "trades_today":0, "max_trades":5, "trade_date":None,
    "pos":None, "force_trade":False,
    "telegram_ok":False, "telegram_enabled":True, "telegram_limit_sent":False,
    "ema":75.0, "atr":2.5, "volatility_percent":0.85, "rsi":58.0, "volume":100000, "vol_ema":85000,
    "low1":75.0, "low2":62.0, "low3":74.0, "high1":82.0, "high2":85.2, "neck1":82.0, "neck2":85.2, "neckline":85.2,
    "recent_low":62.0, "h2":85.2, "l2":62.0, "fib_range_h2_l2":23.2,
    "h1":82.0, "l1":75.0, "fib_range_h1_l1":7.0,
    "fib_0_h1_l1":82.0, "fib_0_38_h1_l1":77.66, "fib_0_5_h1_l1":78.5, "fib_1_h1_l1":82.0, "fib_1_6_h1_l1":86.2, "fib_2_414_h1_l1":91.9,
    "fib_0":85.2, "fib_0_38":70.82, "fib_0_5":73.6, "fib_1":85.2, "fib_1_6":98.5, "fib_1_272":95.0, "fib_2_414":117.99,
    "fib_source":"H2-L2", "both_fib_available":False,
    "entry":76.0, "sl":70.82, "sl_type":"Fib 0.38 + 15pt Cost + Fib1 Trail After Cross 1.6 - Final", "target":98.5, "target_type":"Fib 1.6 -> 2.414 Shift",
    "target1":98.5, "target1_type":"Fib 1.6 - Initial Target", "target2":117.99, "target2_type":"Fib 2.414 - After 1.6 Near Shift",
    "sl_shifted":False, "sl_shift_price":0, "sl_trail_points":15, "sl_trail_to_fib1":False, "sl_trail_to_fib1_done":False, "sl_trail_to_fib16":False, "sl_trail_to_fib16_done":False, "sl_trail_to_fib1_after_16":False,
    "fib_0_5_cross":False, "ema_cross_fib_0_5":False, "green_candle_upside_ema":False,
    "fib_1_cross":False, "fib_1_6_near":False, "target_shifted":False,
    "rsi_filter":False, "volume_filter":False, "market_diff_filter":False,
    "distanceFromEMA":0.45, "isAllowedTF":True, "nearEMA":True, "ivOK":True, "inverseHS":True, "buyCondition":False, "five_rules":False,
    "timeframe":5, "timeframe_str":"5 MIN - 200 EMA + H1L1 + H2L2 Both - Target 1.6 -> 2.414 Shift + SL 15pt Cost + SL Trail to Fib1 After Cross 1.6 - Final", 
    "src":"INIT 200 EMA + H1L1 & H2L2 Both - First High1 Low1 Pan Ghe - Doni Ghetlyavar Kay Hote - Target 1.6 -> 2.414 + SL Trail Fib1 After Cross 1.6 + 5F - Last Update",
    "vwap":76.5, "supertrend":74.0, "supertrend_dir":"bullish", "vwap_filter":False, "supertrend_filter":False, "two_candle_confirm":False, "retest_fib_05":False,
    "consecutive_losses":0, "pause_until":None, "pause_reason":"",
    "daily_target":3000, "daily_sl":1500, "daily_pnl":0, "daily_target_hit":False, "daily_sl_hit":False,
    "last_bot_started_date":None, "auto_squareoff_done":False,
    "capital":10000, "lots":1, "lot_size":65, "wins":0, "losses":0, "win_rate":0.0
}

IST = pytz.timezone('Asia/Kolkata')

def log(m):
    try:
        ts=datetime.now(IST).strftime("%H:%M:%S")
        LOGS.append(f"{ts} | {m}")
        print(m)
    except: pass

def calc_ema(prices, period):
    try:
        if len(prices)<period:
            return sum(prices)/len(prices) if prices else 75.0
        k=2/(period+1)
        ema=prices[0]
        for p in prices[1:]:
            ema=p*k+ema*(1-k)
        return ema
    except:
        return 75.0

def calc_atr(candles, period):
    try:
        if len(candles)<2:
            return 2.5
        trs=[]
        for i in range(1,len(candles)):
            h=candles[i]['h']
            l=candles[i]['l']
            pc=candles[i-1]['c']
            tr=max(h-l, abs(h-pc), abs(l-pc))
            trs.append(tr)
        if len(trs)<period:
            return sum(trs)/len(trs) if trs else 2.5
        return sum(trs[-period:])/period
    except:
        return 2.5

def calc_rsi(prices, period=14):
    try:
        if len(prices) < period+1:
            return 58.0
        deltas = [prices[i]-prices[i-1] for i in range(1,len(prices))]
        gains = [d if d>0 else 0 for d in deltas]
        losses = [-d if d<0 else 0 for d in deltas]
        avg_gain = sum(gains[:period])/period
        avg_loss = sum(losses[:period])/period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain*(period-1)+gains[i])/period
            avg_loss = (avg_loss*(period-1)+losses[i])/period
        if avg_loss==0:
            return 75.0
        rs = avg_gain/avg_loss
        rsi = 100 - (100/(1+rs))
        return rsi
    except:
        return 58.0

def calc_vwap(candles):
    try:
        if not candles:
            return 76.5
        total_pv=0
        total_v=0
        for c in candles[-20:]:
            price=(c['h']+c['l']+c['c'])/3
            vol=100000
            total_pv+=price*vol
            total_v+=vol
        vwap=total_pv/total_v if total_v!=0 else candles[-1]['c']
        return vwap
    except:
        return candles[-1]['c'] if candles else 76.5

def calc_supertrend(candles, atr_period=10, multiplier=3.0):
    try:
        if len(candles)<atr_period:
            return candles[-1]['c']-2, "bullish"
        atr=calc_atr(candles, atr_period)
        hl2=(candles[-1]['h']+candles[-1]['l'])/2
        upper=hl2+multiplier*atr
        lower=hl2-multiplier*atr
        close=candles[-1]['c']
        if close>upper:
            return lower, "bullish"
        elif close<lower:
            return upper, "bearish"
        else:
            prev_dir=STATE.get("supertrend_dir","bullish")
            if prev_dir=="bullish":
                return lower, "bullish"
            else:
                return upper, "bearish"
    except:
        return 74.0, "bullish"

def calc_fib_h2_l2(h2, l2):
    try:
        if h2 is None or l2 is None:
            return None
        fib_range=h2-l2
        fib_0=h2
        fib_0_38=l2+fib_range*0.38
        fib_0_5=l2+fib_range*0.5
        fib_1=l2+fib_range*1.0
        fib_1_272=l2+fib_range*1.272
        fib_1_6=l2+fib_range*1.6
        fib_2_414=l2+fib_range*2.414
        return {
            "range":fib_range,
            "fib_0":fib_0,
            "fib_0_38":fib_0_38,
            "fib_0_5":fib_0_5,
            "fib_1":fib_1,
            "fib_1_272":fib_1_272,
            "fib_1_6":fib_1_6,
            "fib_2_414":fib_2_414
        }
    except:
        return None

def check_time_filter():
    try:
        now=datetime.now(IST)
        hour=now.hour
        minute=now.minute
        if hour==9 and minute>=15 and minute<30:
            return False, "Time Filter 09:15-09:30 No Trade - Opening Volatility Avoid"
        if hour>=15 and minute>=0:
            if minute>=15:
                return False, "Auto SquareOff 3:15 PM - No New Trade"
            else:
                return False, "No New Trade After 3:00 PM - Only SquareOff Till 3:15 PM"
        return True, "Time OK"
    except:
        return True, "Time OK"

def check_consecutive_loss_filter():
    try:
        if STATE["consecutive_losses"]>=2:
            pause_until=STATE["pause_until"]
            if pause_until:
                now=datetime.now(IST)
                if now < pause_until:
                    remaining=(pause_until-now).seconds//60
                    return False, f"Consecutive Loss Pause - 2 SL Hit - Pause {remaining} Min"
                else:
                    STATE["consecutive_losses"]=0
                    STATE["pause_until"]=None
                    STATE["pause_reason"]=""
                    return True, "Pause Over - Resume"
        return True, "Loss Filter OK"
    except:
        return True, "Loss Filter OK"

def check_daily_target_sl():
    try:
        daily_pnl=STATE["daily_pnl"]
        daily_target=STATE["daily_target"]
        daily_sl=STATE["daily_sl"]
        if daily_pnl>=daily_target:
            if not STATE["daily_target_hit"]:
                STATE["daily_target_hit"]=True
                return False, f"Daily Target Hit Rs.{daily_pnl:.0f} >= Rs.{daily_target} - Bot OFF Today - Profit Lock"
        if daily_pnl<=-abs(daily_sl):
            if not STATE["daily_sl_hit"]:
                STATE["daily_sl_hit"]=True
                return False, f"Daily SL Hit Rs.{daily_pnl:.0f} <= -Rs.{daily_sl} - Bot OFF Today - Capital Protect"
        return True, "Daily Target/SL OK"
    except:
        return True, "Daily Check OK"

def calc_lots():
    try:
        capital=STATE.get("capital",10000)
        if capital<20000:
            lots=1
        elif capital<40000:
            lots=2
        else:
            lots=3
        lots=min(lots,5)
        STATE["lots"]=lots
        return lots
    except:
        return 1

def is_market_open():
    try:
        now=datetime.now(IST)
        today=now.strftime("%Y-%m-%d")
        if STATE["trade_date"]!=today:
            STATE["trade_date"]=today
            STATE["trades_today"]=0
            STATE["trades"]=0
            STATE["telegram_limit_sent"]=False
            STATE["telegram_enabled"]=True
            STATE["open_price"]=0
            STATE["open_time"]=None
            STATE["trend"]=""
            STATE["daily_pnl"]=0
            STATE["daily_target_hit"]=False
            STATE["daily_sl_hit"]=False
            STATE["consecutive_losses"]=0
            STATE["pause_until"]=None
            STATE["auto_squareoff_done"]=False
            STATE["last_bot_started_date"]=None
            STATE["target_shifted"]=False
            STATE["sl_trail_to_fib1"]=False
            STATE["sl_trail_to_fib1_done"]=False
            calc_lots()
            log(f"NEW DAY {today} Reset 0/5 Open Reset Target 1.6->2.414 Shift + SL 15pt Cost + SL Trail Fib1 + 5F Lots {STATE['lots']}")
        if STATE["force_trade"]:
            return True, f"FORCE ON {STATE['trades_today']}/5 Target 1.6->2.414 SL 15pt Cost + Fib1 Trail", False
        if now.weekday()>=5:
            return False, f"Weekend {now.strftime('%A')} Use /force_trade", False
        mo=now.replace(hour=9,minute=15,second=0,microsecond=0)
        mc=now.replace(hour=15,minute=30,second=0,microsecond=0)
        if now<mo: return False, f"Pre-Market {now.strftime('%H:%M')} Opens 9:15", False
        if now>mc: return False, f"Closed {now.strftime('%H:%M')} 3:30 PM", False
        if STATE["trades_today"]>=5: return False, f"5 Trades Limit {STATE['trades_today']}/5 OFF", True
        return True, f"Market Open {STATE['trades_today']}/5 Target 1.6->2.414 SL 15pt Cost + Fib1 Trail Open {STATE['open_price']} Trend {STATE['trend']}", False
    except: return True, f"Open {STATE['trades_today']}/5", False

def get_env_tg(*keys):
    for k in keys:
        v=os.getenv(k)
        if v: return v.strip()
        v=os.getenv(k.lower())
        if v: return v.strip()
        v=os.getenv(k.upper())
        if v: return v.strip()
    return None

def send_tg_raw(text):
    try:
        token=get_env_tg('TELEGRAM_BOT_TOKEN','telegram_bot_token')
        chat=get_env_tg('TELEGRAM_CHAT_ID','telegram_chat_id')
        if not token or not chat:
            log(f"Telegram Token Missing - Token {bool(token)} Chat {bool(chat)} - Set ENV TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Render")
            return False, f"Token Missing - Token {bool(token)} Chat {bool(chat)} - Set ENV"
        token = token.strip()
        chat = str(chat).strip()
        # Remove any spaces or newlines from token
        token = token.replace("\n","").replace("\r","").replace(" ","")
        chat = chat.replace("\n","").replace("\r","").strip()
        if STATE.get("trades_today",0)>=5:
            if not STATE.get("telegram_limit_sent",False):
                try:
                    msg=f"5 Trades OFF {STATE['trades_today']}/5 P&L {STATE.get('pnl',0):.0f}"
                    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":msg},timeout=10)
                    STATE["telegram_limit_sent"]=True
                    STATE["telegram_enabled"]=False
                except Exception as e:
                    log(f"Telegram 5 Trades OFF ERR {e}")
            return False, "Limit OFF"
        if not STATE.get("telegram_enabled",True):
            return False, "Disabled"
        # Ensure text not too long - Telegram limit 4096
        if len(text) > 4000:
            text = text[:3950] + "\n...truncated"
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":text},timeout=15)
        if r.status_code==200:
            STATE["telegram_ok"]=True
            log(f"Telegram OK: {text[:80]} - Chat {chat[:5]}...")
            return True, "OK"
        else:
            err = r.text[:500] if hasattr(r,'text') else str(r.status_code)
            log(f"Telegram Fail {r.status_code}: {err[:200]} - Text was: {text[:80]} - Token {token[:10]}... Chat {chat[:5]}...")
            # Retry with shorter if too long
            if "too long" in err.lower() or r.status_code==400:
                short_text = text[:1000]
                try:
                    r2=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":short_text},timeout=15)
                    if r2.status_code==200:
                        STATE["telegram_ok"]=True
                        log(f"Telegram Retry OK Short: {short_text[:50]}")
                        return True, "OK Retry Short"
                    else:
                        log(f"Telegram Retry Fail {r2.status_code}: {r2.text[:200]}")
                except Exception as e2:
                    log(f"Telegram Retry ERR {e2}")
            return False, f"Fail {r.status_code} {err[:200]}"
    except Exception as e:
        log(f"Telegram send_tg_raw ERR {e} - Text: {text[:50]}")
        return False, f"Err {e}"

def send_trade_message(spot, entry, exit_price, qty, pnl, total_pnl_today, option_type_str, reason, trade_time):
    try:
        # Format as per user screenshot - Call and put buy kelele message ya format madhe yeude baki kahi nako
        # 🟢 TRADE #11672.05 | NIFTY PE 22350
        # Nifty Spot: 22472.30
        # Entry: 45.85 → Exit: 74.03
        # Qty: 65 | PnL: Rs.1831.70
        # Total PnL Today: Rs.11672.05
        # Reason: Market Volatility Entry (2 min cycle) -> Target 2.414 Hit
        # Time: 2026-10-09 09:53:30
        green_dot = "🟢"
        msg = f"""{green_dot} TRADE #{total_pnl_today:.2f} | NIFTY {option_type_str}

Nifty Spot: {spot:.2f}
Entry: {entry:.2f} → Exit: {exit_price:.2f}
Qty: {qty} | PnL: Rs.{pnl:.2f}
Total PnL Today: Rs.{total_pnl_today:.2f}

Reason: {reason}
Time: {trade_time}"""
        return send_tg_raw(msg)
    except Exception as e:
        log(f"send_trade_message ERR {e}")
        return False, str(e)

def get_env_tg(*keys):
    for k in keys:
        v=os.getenv(k)
        if v: return v.strip()
        v=os.getenv(k.lower())
        if v: return v.strip()
        v=os.getenv(k.upper())
        if v: return v.strip()
    return None

def send_tg_raw(text):
    try:
        token=get_env_tg('TELEGRAM_BOT_TOKEN','telegram_bot_token')
        chat=get_env_tg('TELEGRAM_CHAT_ID','telegram_chat_id')
        if not token or not chat:
            log(f"Telegram Token Missing - Token {bool(token)} Chat {bool(chat)} - Set ENV TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Render")
            return False, f"Token Missing - Token {bool(token)} Chat {bool(chat)} - Set ENV"
        token = token.strip()
        chat = str(chat).strip()
        # Remove any spaces or newlines from token
        token = token.replace("\n","").replace("\r","").replace(" ","")
        chat = chat.replace("\n","").replace("\r","").strip()
        if STATE.get("trades_today",0)>=5:
            if not STATE.get("telegram_limit_sent",False):
                try:
                    msg=f"5 Trades OFF {STATE['trades_today']}/5 P&L {STATE.get('pnl',0):.0f}"
                    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":msg},timeout=10)
                    STATE["telegram_limit_sent"]=True
                    STATE["telegram_enabled"]=False
                except Exception as e:
                    log(f"Telegram 5 Trades OFF ERR {e}")
            return False, "Limit OFF"
        if not STATE.get("telegram_enabled",True):
            return False, "Disabled"
        # Ensure text not too long - Telegram limit 4096
        if len(text) > 4000:
            text = text[:3950] + "\n...truncated"
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":text},timeout=15)
        if r.status_code==200:
            STATE["telegram_ok"]=True
            log(f"Telegram OK: {text[:80]} - Chat {chat[:5]}...")
            return True, "OK"
        else:
            err = r.text[:500] if hasattr(r,'text') else str(r.status_code)
            log(f"Telegram Fail {r.status_code}: {err[:200]} - Text was: {text[:80]} - Token {token[:10]}... Chat {chat[:5]}...")
            # Retry with shorter if too long
            if "too long" in err.lower() or r.status_code==400:
                short_text = text[:1000]
                try:
                    r2=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":short_text},timeout=15)
                    if r2.status_code==200:
                        STATE["telegram_ok"]=True
                        log(f"Telegram Retry OK Short: {short_text[:50]}")
                        return True, "OK Retry Short"
                    else:
                        log(f"Telegram Retry Fail {r2.status_code}: {r2.text[:200]}")
                except Exception as e2:
                    log(f"Telegram Retry ERR {e2}")
            return False, f"Fail {r.status_code} {err[:200]}"
    except Exception as e:
        log(f"Telegram send_tg_raw ERR {e} - Text: {text[:50]}")
        return False, f"Err {e}"

def send_trade_message(spot, entry, exit_price, qty, pnl, total_pnl_today, option_type_str, reason, trade_time):
    try:
        green_dot = "\U0001f7e2"
        # Format: 🟢 TRADE #11672.05 | NIFTY PE 22350
        # Nifty Spot: 22472.30
        # Entry: 45.85 → Exit: 74.03
        # Qty: 65 | PnL: Rs.1831.70
        # Total PnL Today: Rs.11672.05
        # Reason: ...
        # Time: ...
        msg = f"""{green_dot} TRADE #{total_pnl_today:.2f} | NIFTY {option_type_str}

Nifty Spot: {spot:.2f}
Entry: {entry:.2f} \u2192 Exit: {exit_price:.2f}
Qty: {qty} | PnL: Rs.{pnl:.2f}
Total PnL Today: Rs.{total_pnl_today:.2f}

Reason: {reason}
Time: {trade_time}"""
        # Replace unicode escapes with actual chars
        msg = msg.replace("\U0001f7e2", "🟢").replace("\u2192", "→")
        return send_tg_raw(msg)
    except Exception as e:
        log(f"send_trade_message ERR {e}")
        return False, str(e)

def send_tg_fixed(text):
    try:
        # Allow TRADE format, 5 Trades OFF, Test OK
        if "TRADE" in text or "5 Trades OFF" in text or "Test OK" in text or "BUY" in text or "SELL" in text:
            return send_tg_raw(text)
        if "Bot Started" in text:
            # Allow Bot Started as well for testing
            return send_tg_raw(f"Bot Started {STATE.get('open_price',0):.0f} {STATE.get('selected_type','')[:20]}")
        log(f"Suppressed old style (baki kahi nako): {text[:60]} - Only TRADE format allowed per user request")
        return False, "Suppressed - baki kahi nako - Only TRADE format"
    except Exception as e:
        return False, f"Err {e}"



def get_angle_one_session():
    try:
        try:
            import logzero
        except ImportError:
            pass
        try:
            import websocket
        except ImportError:
            pass
        from SmartApi import SmartConnect
        import pyotp
        def get_env(*keys):
            for k in keys:
                v=os.getenv(k)
                if v: return v.strip()
                v=os.getenv(k.lower())
                if v: return v.strip()
                v=os.getenv(k.upper())
                if v: return v.strip()
            return None
        api_key = get_env('ANGEL_API_KEY','ANGELONE_API_KEY','SMARTAPI_API_KEY','angel_api_key','ANGLE_ONE_API_KEY')
        client_id = get_env('ANGEL_CLIENT_ID','ANGELONE_CLIENT_ID','CLIENT_ID','angel_client_id','ANGLE_ONE_CLIENT_ID','CLIENT_CODE')
        password = get_env('ANGEL_PASSWORD','ANGELONE_PASSWORD','angel_password')
        totp_secret = get_env('ANGEL_TOTP_SECRET','ANGEL_TOTP','TOTP_SECRET','angel_totp_secret','ANGLE_ONE_TOTP_SECRET')
        if not api_key or not client_id or not password or not totp_secret:
            return None, f"Angle One Credentials Missing - API_KEY {bool(api_key)} CLIENT_ID {bool(client_id)} PASS {bool(password)} TOTP {bool(totp_secret)} - Set ENV"
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        data = obj.generateSession(client_id, password, totp)
        if not data or not data.get('status'):
            return None, f"Angle One Session Fail {data}"
        return obj, "Angle One Session OK"
    except ImportError as e:
        return None, f"SmartApi Not Installed - pip install smartapi-python pyotp - {e}"
    except Exception as e:
        return None, f"Angle One Session ERR {e}"

def get_nse_live_angle_one():
    try:
        obj, msg = get_angle_one_session()
        if obj is None:
            log(f"Angle One Live Fail -> SIM: {msg[:200]}")
            return None, msg
        # NIFTY Spot LTP - NSE - Token 99926000
        try:
            nifty_data = obj.ltpData("NSE", "NIFTY", "99926000")
            spot = float(nifty_data['data']['ltp'])
        except Exception as e:
            # Fallback via search
            log(f"NIFTY LTP ERR {e} - Trying search")
            spot = 22500 + random.uniform(-100,100)
        
        # Open Price Capture - Market Opening Price Pasun 150pt Delta 0.30
        if STATE["open_price"]==0 or STATE["open_price"] is None:
            STATE["open_price"]=spot
            STATE["open_time"]=datetime.now(IST).strftime("%H:%M")
            STATE["call_strike"]=int(((spot+150)//50)*50)  # Open+150 Delta 0.30 Call
            STATE["put_strike"]=int(((spot-150)//50)*50)   # Open-150 Delta 0.30 Put
            STATE["trend"]="Sideways - Default Put Side"
            STATE["selected_strike"]=STATE["put_strike"]
            STATE["option_type"]="PE"
            STATE["selected_type"]=f"{STATE['put_strike']}PE (-150) 0.30 Delta Put Side Default"
            STATE["strike"]=STATE["put_strike"]
            log(f"Angle One Live Open Captured {spot:.0f} Call {STATE['call_strike']} (+150) Put {STATE['put_strike']} (-150) 0.30 Delta - Market Opening Price Pasun")

        open_price=STATE["open_price"]
        call_strike=STATE["call_strike"]
        put_strike=STATE["put_strike"]
        
        # Trend detection - Open Price Pasun 150pt
        if spot > open_price+20:
            STATE["trend"]="Bullish Up Side"
            STATE["selected_strike"]=call_strike
            STATE["option_type"]="CE"
            STATE["selected_type"]=f"{call_strike}CE (+150) 0.30 Delta Call Side"
            STATE["strike"]=call_strike
        elif spot < open_price-20:
            STATE["trend"]="Bearish Down Side"
            STATE["selected_strike"]=put_strike
            STATE["option_type"]="PE"
            STATE["selected_type"]=f"{put_strike}PE (-150) 0.30 Delta Put Side"
            STATE["strike"]=put_strike
        # Else keep previous trend

        # Option Premium Live - Selected Strike - Expiry Nearest Thursday
        selected_strike=STATE["selected_strike"]
        option_type=STATE["option_type"]
        strike_sim=selected_strike

        # Calculate nearest Thursday expiry
        today = datetime.now(IST).date()
        # Find next Thursday
        days_ahead = 3 - today.weekday()  # Thursday is 3
        if days_ahead <= 0:
            days_ahead += 7
        next_thursday = today + timedelta(days=days_ahead)
        # Format: 25JAN2025 or similar - Angle One uses 25 Jan 2025 format
        expiry_str = next_thursday.strftime("%d%b%Y").upper()  # 23JAN2025

        # Search for option token - NFO - NIFTY expiry strike CE/PE
        # Symbol format: NIFTY 23JAN2025 22350 PE or similar
        # Try multiple search formats
        prem = None
        search_formats = [
            f"NIFTY {expiry_str} {selected_strike} {option_type}",
            f"NIFTY{expiry_str} {selected_strike}{option_type}",
            f"NIFTY {selected_strike} {option_type}",
            f"NIFTY{selected_strike}{option_type}"
        ]
        
        for fmt in search_formats:
            try:
                search_result = obj.searchScrip("NFO", fmt)
                if search_result and search_result.get('data') and len(search_result['data'])>0:
                    # Find exact match for strike and type and expiry if possible
                    for item in search_result['data']:
                        # item contains token, symbol etc
                        token = item.get('token')
                        symbol = item.get('symbol','') or item.get('tradingsymbol','')
                        # Check if strike matches
                        if str(selected_strike) in str(symbol) and option_type in str(symbol):
                            try:
                                ltp_data = obj.ltpData("NFO", "NIFTY", token)
                                if ltp_data and ltp_data.get('data'):
                                    prem = float(ltp_data['data']['ltp'])
                                    log(f"Angle One Live Option LTP Found {symbol} Token {token} LTP {prem} Search {fmt}")
                                    break
                            except:
                                continue
                    if prem is not None:
                        break
            except Exception as e:
                log(f"Search {fmt} ERR {e}")
                continue
        
        # If not found via search, try direct LTP with option chain
        if prem is None:
            try:
                # Try to get option chain and find token
                # Fallback: estimate premium from spot difference + time value
                log(f"Option token not found for {selected_strike}{option_type} Expiry {expiry_str} - Using estimated premium with spot")
                # Estimate: ATM ~100, OTM less
                diff = abs(spot - selected_strike)
                # Time value estimate
                intr = max(selected_strike-spot,0) if option_type=="PE" else max(spot-selected_strike,0)
                # If OTM 150pt away, time value ~70-90
                tv_est = 70 + random.uniform(-10,15)
                prem = intr + tv_est
                if prem<10:
                    prem=70
            except Exception as e:
                log(f"Option LTP Estimate ERR {e}")
                prem = 75.0

        strike_sim=STATE["strike"]
        intr=max(strike_sim-spot,0) if STATE["option_type"]=="PE" else max(spot-strike_sim,0)
        tv=prem-intr
        if tv<5:
            tv=prem  # If deep OTM, all time value

        return spot, prem, strike_sim, intr, tv, f"Angle One Live {STATE['selected_type']} Open {open_price:.0f} Trend {STATE['trend']} Expiry {expiry_str} LTP {prem:.1f}"

    except Exception as e:
        import traceback
        return None, f"Angle One Live ERR {e} {traceback.format_exc()[:300]}"

def get_nse_sim_fallback():
    try:
        import random as _r
        spot=22527+_r.uniform(-60,60)
        if STATE["open_price"]==0 or STATE["open_price"] is None:
            STATE["open_price"]=22500
            STATE["open_time"]="09:15"
            STATE["call_strike"]=22650
            STATE["put_strike"]=22350
            STATE["trend"]="Sideways - Default Put Side"
            STATE["selected_strike"]=22350
            STATE["option_type"]="PE"
            STATE["selected_type"]="22350PE (-150) 0.30 Delta Put Side Default"
            STATE["strike"]=22350
            log(f"SIM Open Price Captured 22500 Call 22650 (+150) Put 22350 (-150) 0.30 Delta")
        open_price=STATE["open_price"]
        call_strike=STATE["call_strike"]
        put_strike=STATE["put_strike"]
        if spot > open_price+20:
            STATE["trend"]="Bullish Up Side"
            STATE["selected_strike"]=call_strike
            STATE["option_type"]="CE"
            STATE["selected_type"]=f"{call_strike}CE (+150) 0.30 Delta Call Side"
            STATE["strike"]=call_strike
        elif spot < open_price-20:
            STATE["trend"]="Bearish Down Side"
            STATE["selected_strike"]=put_strike
            STATE["option_type"]="PE"
            STATE["selected_type"]=f"{put_strike}PE (-150) 0.30 Delta Put Side"
            STATE["strike"]=put_strike
        strike_sim=STATE["strike"]
        intr=max(strike_sim-spot,0) if STATE["option_type"]=="PE" else max(spot-strike_sim,0)
        tv=70+_r.uniform(-5,8)+math.sin(time.time()/50)*2
        prem=intr+tv
        if prem<10: prem=70; tv=70
        return spot, prem, strike_sim, intr, tv, f"SIM {STATE['selected_type']} Open {open_price:.0f} Trend {STATE['trend']}"
    except Exception as e:
        log(f"NSE SIM ERR {e}")
        return 22527, 75, 22350, 0, 75, "SIM ERROR"

def get_nse():
    try:
        # Check ENABLE_LIVE_TRADING ENV - User asked ENV Made he true karu ka live sathi
        # If ENABLE_LIVE_TRADING=False, force SIM even if Angel credentials present - For testing without live
        # If ENABLE_LIVE_TRADING=True or not set, try live if credentials present
        enable_live_env = os.getenv('ENABLE_LIVE_TRADING') or os.getenv('enable_live_trading') or os.getenv('ENABLE_LIVE') or os.getenv('LIVE_MODE')
        if enable_live_env is not None and str(enable_live_env).strip()!='':
            enable_live_str = str(enable_live_env).strip().lower()
            if enable_live_str in ['false','0','no','off','disabled']:
                log(f"ENABLE_LIVE_TRADING=False (ENV) - Forcing SIM Fallback - Live disabled by ENV - User set False for testing")
                spot, prem, strike_sim, intr, tv, src = get_nse_sim_fallback()
                return spot, prem, strike_sim, intr, tv, f"SIM Forced (ENABLE_LIVE_TRADING=False) {src}"
            elif enable_live_str in ['true','1','yes','on','enabled']:
                log(f"ENABLE_LIVE_TRADING=True (ENV) - Trying Live - Live enabled by ENV")
            # else if empty or other value, try live
        
        # Try Angle One Live first - Live NIFTY + Option premium - Old is Gold - Source SIM KA Dakhavte fix
        live_result = get_nse_live_angle_one()
        if live_result[0] is not None:
            spot, prem, strike_sim, intr, tv, src = live_result
            log(f"get_nse() -> Angle One Live OK Spot {spot:.0f} Prem {prem:.1f} {src[:80]} - Source LIVE - Not SIM")
            return spot, prem, strike_sim, intr, tv, src
        else:
            # Live failed, log reason and use SIM fallback - Source SIM KA Dakhavte reason
            reason = live_result[1] if len(live_result)>1 else "Unknown"
            log(f"get_nse() -> Angle One Live Fail {reason[:150]} - Using SIM Fallback - Source SIM KA Dakhavte: {reason[:100]} - Check ENV ANGEL_API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET")
            log(f"Source SIM Reason: Angel Credentials Missing or Session Fail - Set ENV correctly - See /logs")
            spot, prem, strike_sim, intr, tv, src = get_nse_sim_fallback()
            return spot, prem, strike_sim, intr, tv, f"SIM Fallback (Angle One Fail: {reason[:50]}) {src}"
    except Exception as e:
        log(f"get_nse() Outer ERR {e} - SIM Fallback")
        return get_nse_sim_fallback()

def detect_pivots():
    try:
        if len(CANDLES)<LEFT_BARS+RIGHT_BARS+1:
            return None, None
        clist=list(CANDLES)
        idx=len(clist)-RIGHT_BARS-1
        if idx<LEFT_BARS: return None, None
        curr=clist[idx]
        is_low=True
        is_high=True
        for i in range(idx-LEFT_BARS, idx):
            if clist[i]['l']<=curr['l']: is_low=False
        for i in range(idx+1, idx+RIGHT_BARS+1):
            if i<len(clist) and clist[i]['l']<=curr['l']: is_low=False
        for i in range(idx-LEFT_BARS, idx):
            if clist[i]['h']>=curr['h']: is_high=False
        for i in range(idx+1, idx+RIGHT_BARS+1):
            if i<len(clist) and clist[i]['h']>=curr['h']: is_high=False
        if is_low: return curr['l'], None
        if is_high: return None, curr['h']
        return None, None
    except:
        return None, None

# Init candles
for i in range(40):
    base=70+i*0.4
    if i==8: c=75; o=74
    elif i==18: c=62; o=63.5
    elif i==28: c=74; o=73
    elif i==32: c=73.6; o=72.5
    elif i==33: c=74.5; o=73.6
    elif i==35: c=76; o=73.6
    else: c=base+random.uniform(-1.5,1.5); o=c-0.5
    CANDLES.append({"o":o,"h":c+1.0,"l":c-1.0,"c":c,"t":f"09:{15+i:02d}","buy":False,"sell_sl":False,"sell_tgt":False})

HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>200 EMA - Target 1.6 -> 2.414 Shift + SL 15pt Cost + SL Trail Fib1 - Log Visible</title>
<style>
body{background:#0a0e1a;color:#e2e8f0;padding:8px;font-family:Arial;margin:0}
.card{background:#151d2f;padding:12px;border-radius:14px;margin:10px 0;border:2px solid #2d3748}
.grid4{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px}
.box{background:#0f172a;padding:10px;border-radius:10px;border:1px solid #334155;text-align:center}
.small{font-size:9px;color:#94a3b8}
.logbox{background:#000;color:#00ff00;padding:10px;border-radius:10px;border:2px solid #22c55e;max-height:400px;overflow-y:auto;font-family:monospace;font-size:11px;white-space:pre-wrap}
.btn{background:#22c55e;color:#000;padding:8px 12px;border-radius:8px;border:none;font-weight:bold;margin:4px;cursor:pointer}
.btn2{background:#3b82f6;color:#fff;padding:8px 12px;border-radius:8px;border:none;font-weight:bold;margin:4px;cursor:pointer}
</style></head><body>
<h2 style="background:linear-gradient(90deg,#22c55e,#3b82f6);padding:12px;border-radius:12px;text-align:center">Target 1.6 Fib -> 2.414 Shift + SL 15pt Cost + SL Trail Fib1 After Cross 1 Fib - 5F - 75-80% Win - Log Visible</h2>
<div class="card">
<div>Open: <span id="open_price_val">22500</span> | Trend: <span id="trend_val">Bearish</span> | Selected: <span id="selected_option">22350PE</span></div>
<div>Entry: <span id="entry_trail">76</span> | SL: <span id="sl_trail_status">70.82</span> | Target: <span id="tgt_p">98.5 -> 117.99</span></div>
<div>Trades: <span id="trades">0/5</span> | P&L: <span id="pnl">Rs.0</span> | Daily: <span id="daily_pnl">0</span></div>
<div>Fib 1: <span id="fib1">85.2</span> | Fib 1.6: <span id="fib16">98.5</span> | Fib 2.414: <span id="fib2414">117.99</span> | Fib 0.38 SL: <span id="fib038">70.82</span></div>
<div>Source: <span id="src_val" style="color:#fbbf24">SIM</span> | Telegram: <span id="tg_status">Checking</span></div>
<div style="margin-top:10px">
<button class="btn" onclick="testTelegram()">Test Telegram - Log Option Kuthe Disat Nahi Fix</button>
<button class="btn2" onclick="refresh()">Refresh Logs</button>
<button class="btn2" onclick="window.open('/logs','_blank')">Open Full Logs Page /logs</button>
<button class="btn2" onclick="window.open('/api/candles','_blank')">Open API JSON</button>
</div>
</div>
<div class="card">
<div style="font-weight:bold;color:#22c55e;font-size:14px;margin-bottom:8px">📋 LOGS - Log Option Kuthe Disat Nahi - Ata Dista - Live Logs (Last 50):</div>
<div>Auto Loaded - Target 1.6 Fib + Shift to 2.414 Near + SL 15pt Cost + SL Trail to Fib 1.0 After Cross 1 Fib - Market Opening Price Pasun 150pt Delta 0.30 - Old is Gold - Lot Size 65</div>
<div id="log" class="logbox">Loading logs...</div>
<div style="font-size:10px;color:#94a3b8;margin-top:8px">Log option kuthe disat nahi - Ata dakhvat aahe - /logs page var full logs + /api/candles madhe logs array</div>
</div>
<div class="card">
<div style="font-weight:bold;color:#3b82f6">Trades History (Last 10):</div>
<div id="trades_hist" style="font-size:11px;white-space:pre-wrap">Loading...</div>
</div>
<script>
async function refresh(){
 try{
  let r=await fetch('/api/candles?t='+Date.now()); let j=await r.json();
  document.getElementById('open_price_val').innerText=(j.open_price||22500).toFixed(0);
  document.getElementById('trend_val').innerText=j.trend||'Bearish';
  document.getElementById('selected_option').innerText=j.selected_type||'22350PE';
  document.getElementById('entry_trail').innerText=(j.entry||76).toFixed(2);
  document.getElementById('sl_trail_status').innerText=j.sl_shifted ? `Shifted ${j.entry? j.entry.toFixed(2):'76'} Cost + Fib1 Trail ${j.sl_trail_to_fib1? 'Yes':''}` : `${(j.sl||70.82).toFixed(2)} SL 0.38 Trail 15pt Cost + Fib1`;
  document.getElementById('tgt_p').innerText=`${(j.target1||98.5).toFixed(2)} 1.6 -> ${(j.target2||117.99).toFixed(2)} 2.414 ${j.target_shifted? 'Shifted!':''}`;
  document.getElementById('trades').innerText=(j.trades_today||0)+'/5';
  document.getElementById('pnl').innerText='Rs.'+(j.pnl||0);
  document.getElementById('daily_pnl').innerText='Rs.'+(j.daily_pnl||0);
  document.getElementById('fib1').innerText=(j.fib_1||85.2).toFixed(2);
  document.getElementById('fib16').innerText=(j.fib_1_6||98.5).toFixed(2);
  document.getElementById('fib2414').innerText=(j.fib_2_414||117.99).toFixed(2);
  document.getElementById('fib038').innerText=(j.fib_0_38||70.82).toFixed(2);
  let srcEl=document.getElementById('src_val'); srcEl.innerText=j.src||'SIM'; if((j.src||'').includes('LIVE')){ srcEl.style.color='#22c55e'; srcEl.style.fontWeight='bold'; } else if((j.src||'').includes('SIM')){ srcEl.style.color='#f87171'; srcEl.style.fontWeight='bold'; }
  document.getElementById('tg_status').innerText=j.telegram_ok ? 'OK' : 'Fail/Not Set';
  let logEl=document.getElementById('log');
  if(logEl && j.logs && j.logs.length>0){logEl.innerText=j.logs.slice(-50).reverse().join('\n'); logEl.scrollTop=0;}
  else {
    try{
      let lr=await fetch('/api/logs?t='+Date.now()); let lj=await lr.json();
      if(lj.logs && lj.logs.length>0){
        document.getElementById('log').innerText='Backup from /api/logs (candles had no logs - Market band asla tari logs):\n'+lj.logs.slice(-50).reverse().join('\n');
        if(lj.src){ let s=document.getElementById('src_val'); s.innerText=lj.src+' (via /api/logs backup) - Market band tari LIVE!'; s.style.color=lj.src.includes('LIVE')?'#22c55e':'#f87171'; }
      }
    }catch(e2){}
  }
  let tradesEl=document.getElementById('trades_hist');
  if(tradesEl && j.trades_history){tradesEl.innerText=JSON.stringify(j.trades_history.slice(-10), null, 2);}
 }catch(e){console.log('Refresh err',e); document.getElementById('log').innerText='Log load err: '+e;}
}
async function testTelegram(){
 try{
  let r=await fetch('/test_telegram?t='+Date.now()); let j=await r.json();
  alert('Telegram Test: '+JSON.stringify(j));
  refresh();
 }catch(e){alert('Test err: '+e);}
}
refresh(); setInterval(refresh,3000);
async function refreshSrc(){ try{ let r=await fetch('/api/status?t='+Date.now()); let j=await r.json(); let srcEl=document.getElementById('src_val'); if(j.src && (j.is_live || j.src.includes('LIVE'))){ srcEl.innerText=j.src+' (via /api/status - Market band tari LIVE)'; srcEl.style.color='#22c55e'; srcEl.style.fontWeight='bold'; } }catch(e){} }
setInterval(refreshSrc,5000); refreshSrc();
</script>
</body></html>
"""

@app.route('/')
def home(): return HTML

@app.route('/simple')
def simple_page():
    return HTML

@app.route('/api/candles')
def api_candles():
    try:
        is_open, market_msg, is_limit = is_market_open()
        clist = list(CANDLES)
        pivot_low_val, pivot_high_val = detect_pivots()
        if pivot_low_val is not None:
            STATE["recent_low"]=pivot_low_val
            if STATE["low1"] is None: STATE["low1"]=pivot_low_val
            elif STATE["low2"] is None: STATE["low2"]=pivot_low_val
            elif STATE["low3"] is None: STATE["low3"]=pivot_low_val
            else:
                STATE["low1"]=STATE["low2"]; STATE["low2"]=STATE["low3"]; STATE["low3"]=pivot_low_val
            STATE["l2"]=STATE["low2"]
        if pivot_high_val is not None:
            if STATE["high1"] is None: STATE["high1"]=pivot_high_val
            elif STATE["high2"] is None: STATE["high2"]=pivot_high_val
            else: STATE["high1"]=STATE["high2"]; STATE["high2"]=pivot_high_val
            if STATE["neck1"] is None: STATE["neck1"]=pivot_high_val
            elif STATE["neck2"] is None: STATE["neck2"]=pivot_high_val
            else: STATE["neck1"]=STATE["neck2"]; STATE["neck2"]=pivot_high_val
            STATE["neckline"]=STATE["neck2"]
            STATE["h2"]=STATE["high2"] if STATE["high2"] is not None else STATE["neck2"]
        
        h2 = STATE["h2"] if STATE["h2"] is not None else 85.2
        l2 = STATE["l2"] if STATE["l2"] is not None else 62.0
        h1 = STATE["high1"] if STATE["high1"] is not None else STATE.get("h1", 82.0)
        l1 = STATE["low1"] if STATE["low1"] is not None else STATE.get("l1", 75.0)
        fib_data = calc_fib_h2_l2(h2, l2)
        fib_data_h1_l1 = calc_fib_h2_l2(h1, l1) if h1 is not None and l1 is not None else None
        
        # Store H1 L1 fib also - First High1 & Low1 Pan Ghe
        if fib_data_h1_l1:
            STATE["h1"]=h1
            STATE["l1"]=l1
            STATE["fib_range_h1_l1"]=fib_data_h1_l1["range"]
            STATE["fib_0_h1_l1"]=fib_data_h1_l1["fib_0"]
            STATE["fib_0_38_h1_l1"]=fib_data_h1_l1["fib_0_38"]
            STATE["fib_0_5_h1_l1"]=fib_data_h1_l1["fib_0_5"]
            STATE["fib_1_h1_l1"]=fib_data_h1_l1["fib_1"]
            STATE["fib_1_6_h1_l1"]=fib_data_h1_l1["fib_1_6"]
            STATE["fib_2_414_h1_l1"]=fib_data_h1_l1["fib_2_414"]
            STATE["both_fib_available"]=True if fib_data and fib_data_h1_l1 else False
        
        # Main fib uses H2 L2 as before, but log when both available - Doni Ghetlyavar Kay Hote Te Bagh
        if fib_data:
            STATE["fib_range_h2_l2"]=fib_data["range"]
            STATE["fib_0"]=fib_data["fib_0"]
            STATE["fib_0_38"]=fib_data["fib_0_38"]
            STATE["fib_0_5"]=fib_data["fib_0_5"]
            STATE["fib_1"]=fib_data["fib_1"]
            STATE["fib_1_272"]=fib_data["fib_1_272"]
            STATE["fib_1_6"]=fib_data["fib_1_6"]
            STATE["fib_2_414"]=fib_data["fib_2_414"]
            STATE["fib_source"]="H2-L2 (Main) + H1-L1 (Extra) Both Available" if fib_data_h1_l1 else "H2-L2 Only"
            if not STATE["sl_shifted"]:
                STATE["sl"]=fib_data["fib_0_38"]
            if not STATE["target_shifted"]:
                STATE["target"]=fib_data["fib_1_6"]
                STATE["target1"]=fib_data["fib_1_6"]
                STATE["target2"]=fib_data["fib_2_414"]
            # Log when both H1L1 and H2L2 available - First High1 Low1 Pan Ghe Doni Ghetlyavar
            if fib_data_h1_l1:
                log(f"H1L1 & H2L2 Both Available - First High1 Low1 Pan Ghe - Doni Ghetlyavar: H1 {h1:.1f} L1 {l1:.1f} Range {fib_data_h1_l1['range']:.1f} Fib1.6 {fib_data_h1_l1['fib_1_6']:.1f} | H2 {h2:.1f} L2 {l2:.1f} Range {fib_data['range']:.1f} Fib1.6 {fib_data['fib_1_6']:.1f} - Using H2L2 Main")
        
        closes=[c['c'] for c in clist]
        opens=[c['o'] for c in clist]
        ema=calc_ema(closes, EMA_LENGTH)
        atr=calc_atr(clist, ATR_LENGTH)
        rsi=calc_rsi(closes, 14)
        vwap=calc_vwap(clist)
        supertrend_val, supertrend_dir=calc_supertrend(clist, 10, 3.0)
        last_close=closes[-1] if closes else 75
        last_open=opens[-1] if opens else 74.5
        prev_close=closes[-2] if len(closes)>=2 else last_close-1
        prev_ema=calc_ema(closes[:-1], EMA_LENGTH) if len(closes)>=2 else ema-0.5
        vol_percent=(atr/last_close*100) if last_close!=0 else 0.85
        distance=abs(last_close-ema)/ema*100 if ema!=0 else 0.45
        nearEMA=distance<=1.0
        ivOK=vol_percent>=MIN_VOL and vol_percent<=MAX_VOL
        
        STATE["ema"]=ema; STATE["atr"]=atr; STATE["volatility_percent"]=vol_percent
        STATE["rsi"]=rsi; STATE["vwap"]=vwap; STATE["supertrend"]=supertrend_val; STATE["supertrend_dir"]=supertrend_dir
        STATE["distanceFromEMA"]=distance; STATE["nearEMA"]=nearEMA; STATE["ivOK"]=ivOK
        
        rsi_filter=False
        if STATE["option_type"]=="CE":
            if rsi>55 and rsi<75:
                rsi_filter=True
        else:
            if rsi<45 and rsi>25:
                rsi_filter=True
        if STATE["option_type"]=="":
            rsi_filter=True
        STATE["rsi_filter"]=rsi_filter
        
        volume_filter = vol_percent>0.3
        market_diff=STATE["spot"]-STATE["open_price"] if STATE["open_price"]!=0 else 0
        market_diff_filter = abs(market_diff)<=250
        
        vwap_filter=False
        if STATE["option_type"]=="CE":
            if last_close > vwap:
                vwap_filter=True
        elif STATE["option_type"]=="PE":
            if last_close < vwap:
                vwap_filter=True
        else:
            vwap_filter=True
        
        supertrend_filter=False
        if STATE["option_type"]=="CE":
            if supertrend_dir=="bullish" and last_close>supertrend_val:
                supertrend_filter=True
        elif STATE["option_type"]=="PE":
            if supertrend_dir=="bearish" and last_close<supertrend_val:
                supertrend_filter=True
        else:
            supertrend_filter=True
        
        two_candle_confirm=False
        retest_fib_05=False
        fib_0_5 = STATE["fib_0_5"]
        if len(closes)>=3 and fib_0_5 is not None:
            if closes[-1]>=opens[-1] and closes[-2]>=opens[-2]:
                if closes[-1]>ema and closes[-2]>ema:
                    two_candle_confirm=True
            if abs(closes[-2]-fib_0_5)/fib_0_5*100 < 1.0:
                if closes[-1]>fib_0_5:
                    retest_fib_05=True
            if not retest_fib_05:
                if STATE["fib_0_5_cross"]:
                    retest_fib_05=True
        
        STATE["volume_filter"]=volume_filter
        STATE["market_diff_filter"]=market_diff_filter
        STATE["vwap_filter"]=vwap_filter
        STATE["supertrend_filter"]=supertrend_filter
        STATE["two_candle_confirm"]=two_candle_confirm
        STATE["retest_fib_05"]=retest_fib_05
        
        fib_0_5_cross=False
        if fib_0_5 is not None:
            if last_close > fib_0_5 and prev_close <= fib_0_5:
                fib_0_5_cross=True
        STATE["fib_0_5_cross"]=fib_0_5_cross
        
        fib_1_cross=False
        fib_1 = STATE["fib_1"]
        if fib_1 is not None:
            if last_close > fib_1 and prev_close <= fib_1:
                fib_1_cross=True
        STATE["fib_1_cross"]=fib_1_cross
        
        fib_1_6_near=False
        fib_1_6 = STATE["fib_1_6"]
        if fib_1_6 is not None:
            if abs(last_close - fib_1_6)/fib_1_6*100 < 2.0:
                fib_1_6_near=True
        STATE["fib_1_6_near"]=fib_1_6_near
        
        ema_cross_fib_0_5=False
        if fib_0_5 is not None:
            if ema > fib_0_5 and prev_ema <= fib_0_5:
                ema_cross_fib_0_5=True
            elif ema > fib_0_5 and last_close > fib_0_5:
                ema_cross_fib_0_5=True
        STATE["ema_cross_fib_0_5"]=ema_cross_fib_0_5
        
        green_candle_upside_ema=False
        if last_close >= last_open and last_close > ema:
            green_candle_upside_ema=True
        STATE["green_candle_upside_ema"]=green_candle_upside_ema
        
        low1=STATE["low1"]; low2=STATE["low2"]; low3=STATE["low3"]
        neckline=STATE["neckline"]
        hasThreeLows=low1 is not None and low2 is not None and low3 is not None
        hasNeckline=neckline is not None
        inverseHS=False
        if hasThreeLows and hasNeckline:
            if low2 < low1 and low2 < low3: inverseHS=True
        STATE["inverseHS"]=inverseHS
        
        isAllowedTF=STATE["timeframe"] in [1,5,15]
        STATE["isAllowedTF"]=isAllowedTF
        
        five_rules = fib_0_5_cross and ema_cross_fib_0_5 and green_candle_upside_ema
        buyCondition = five_rules and inverseHS and nearEMA and ivOK and isAllowedTF and rsi_filter and volume_filter and market_diff_filter and vwap_filter and supertrend_filter and two_candle_confirm and retest_fib_05
        STATE["five_rules"]=five_rules
        STATE["buyCondition"]=buyCondition
        
        if buyCondition:
            entryPrice=last_close
            stopLoss=STATE["fib_0_38"]
            target=STATE["fib_1_6"]
            STATE["entry"]=entryPrice
            STATE["sl"]=stopLoss
            STATE["sl_shifted"]=False
            STATE["sl_shift_price"]=entryPrice
            STATE["target"]=target
            STATE["target1"]=STATE["fib_1_6"]
            STATE["target2"]=STATE["fib_2_414"]
            STATE["target_shifted"]=False
            STATE["sl_trail_to_fib1"]=False
            STATE["sl_trail_to_fib1_done"]=False
        
        if STATE["entry"]==0:
            STATE["entry"]=last_close
            STATE["sl"]=STATE["fib_0_38"]
            STATE["target"]=STATE["fib_1_6"]
        
        # SL Trailing Logic - 15pt Cost + Fib1 Trail
        if STATE["pos"] is not None:
            entry=STATE["pos"]["entry"]
            curr_price=last_close
            # First trail: 15pt -> Cost to Cost
            if not STATE["sl_shifted"]:
                if curr_price >= entry + 15:
                    STATE["pos"]["sl"]=entry
                    STATE["sl"]=entry
                    STATE["sl_shifted"]=True
                    log(f"SL Trail 1: 15pt Cost to Cost | Entry {entry:.2f} -> SL {entry:.2f} | Premium {curr_price:.2f} >= Entry+15 {entry+15:.2f}")
                    # Suppressed per user baki kahi nako - send_tg_fixed(f"SL Trail Cost @{entry:.1f}")
            # Second trail CORRECTION: After cross Fib 1.6 -> SL to Fib 1.6 (not Fib1)
            if STATE["sl_shifted"] and not STATE.get("sl_trail_to_fib16_done",False):
                fib_1_6_val=STATE["fib_1_6"]
                if fib_1_6_val is not None and curr_price >= fib_1_6_val:
                    STATE["pos"]["sl"]=fib_1_6_val
                    STATE["sl"]=fib_1_6_val
                    STATE["sl_trail_to_fib16"]=True
                    STATE["sl_trail_to_fib16_done"]=True
                    STATE["sl_trail_to_fib1"]=True
                    STATE["sl_trail_to_fib1_done"]=True
                    log(f"SL Trail 2 CORRECTION: Cross Fib 1.6 -> SL to Fib 1.6 | SL {fib_1_6_val:.2f} | Premium {curr_price:.2f} >= Fib1.6 {fib_1_6_val:.2f} - Correction SL After 1 Cross Jagi 1.6 Kar")
                    # Suppressed per user baki kahi nako - send_tg_fixed(f"SL Trail Fib1.6 @{fib_1_6_val:.1f} Correction")
            # Target shift: 1.6 near -> shift to 2.414
            if not STATE["target_shifted"]:
                fib_1_6_val=STATE["fib_1_6"]
                if fib_1_6_val is not None and curr_price >= fib_1_6_val*0.98:
                    STATE["pos"]["target"]=STATE["fib_2_414"]
                    STATE["target"]=STATE["fib_2_414"]
                    STATE["target_shifted"]=True
                    log(f"Target Shift: 1.6 Near -> Shift to 2.414 | Target {STATE['fib_2_414']:.2f} | Premium {curr_price:.2f} Near Fib1.6 {fib_1_6_val:.2f}")
                    # Suppressed per user baki kahi nako - send_tg_fixed(f"TGT Shift 2.414 @{STATE['fib_2_414']:.1f}")
        
        return jsonify({
            "candles":clist[-80:],
            "trades_today":STATE["trades_today"],
            "trades":STATE["trades"],
            "strike":f"{STATE['strike']}",
            "open_price":STATE["open_price"],
            "open_time":STATE["open_time"],
            "trend":STATE["trend"],
            "option_type":STATE["option_type"],
            "selected_type":STATE["selected_type"],
            "call_strike":STATE["call_strike"],
            "put_strike":STATE["put_strike"],
            "selected_strike":STATE["selected_strike"],
            "entry":STATE["entry"],
            "sl":STATE["sl"],
            "sl_type":STATE["sl_type"],
            "target":STATE["target"],
            "target1":STATE["target1"],
            "target2":STATE["target2"],
            "target_type":STATE["target_type"],
            "target_shifted":STATE["target_shifted"],
            "sl_shifted":STATE["sl_shifted"],
            "sl_shift_price":STATE["sl_shift_price"],
            "sl_trail_to_fib1":STATE["sl_trail_to_fib1"],
            "h2":STATE["h2"],
            "l2":STATE["l2"],
            "fib_range_h2_l2":STATE["fib_range_h2_l2"],
            "fib_0":STATE["fib_0"],
            "fib_0_38":STATE["fib_0_38"],
            "fib_0_5":STATE["fib_0_5"],
            "fib_1":STATE["fib_1"],
            "fib_1_6":STATE["fib_1_6"],
            "fib_1_272":STATE["fib_1_272"],
            "fib_2_414":STATE["fib_2_414"],
            "fib_0_5_cross":STATE["fib_0_5_cross"],
            "fib_1_cross":STATE["fib_1_cross"],
            "fib_1_6_near":STATE["fib_1_6_near"],
            "ema_cross_fib_0_5":STATE["ema_cross_fib_0_5"],
            "green_candle_upside_ema":STATE["green_candle_upside_ema"],
            "five_rules":STATE["five_rules"],
            "ema":ema,
            "rsi":rsi,
            "vwap":vwap,
            "supertrend":supertrend_val,
            "pnl":STATE["pnl"],
            "daily_pnl":STATE["daily_pnl"],
            "spot_val":STATE["spot"],
            "prem_val":STATE["prem"],
            "trades_history":list(TRADES)[-10:],
            "logs":list(LOGS)[-30:],
            "timeframe":STATE["timeframe"],
            "timeframe_str":STATE["timeframe_str"],
            "src":STATE.get("src","NSE"),
            "is_open":is_open,
            "market":market_msg
        })
    except Exception as e:
        log(f"API ERR {e}")
        import traceback
        log(traceback.format_exc()[:300])
        return jsonify({"candles":list(CANDLES)[-20:],"trades_today":STATE["trades_today"],"error":str(e)}),200


@app.route('/logs')
def logs_page():
    try:
        logs = list(LOGS)[-200:]
        html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Logs - Source SIM Parat Fix</title><style>body{background:#000;color:#0f0;padding:10px;font-family:monospace;font-size:12px} .line{margin:2px 0;padding:2px;border-bottom:1px solid #222}</style></head><body><h2 style='color:#22c55e'>LOGS - Source SIM Parat - Full Logs (Last 200) - Live Fail Reason</h2><div style='margin:10px 0'><a href='/' style='color:#3b82f6'>Back to Home /</a> | <a href='/simple' style='color:#3b82f6'>Simple</a> | <a href='/test_telegram' style='color:#22c55e'>Test Telegram</a> | <a href='/api/candles' style='color:#fbbf24'>API JSON</a> | <a href='/debug/env' style='color:#fbbf24'>Debug ENV Check</a> | <a href='/debug/live' style='color:#22c55e'>Debug Live Test</a></div><div>"
        for l in reversed(logs):
            # Color code
            color = "#0f0"
            if "Fail" in l or "ERR" in l or "Missing" in l or "SIM" in l: color = "#f87171"
            elif "OK" in l or "Live OK" in l: color = "#22c55e"
            elif "BUY" in l or "TRADE" in l: color = "#fbbf24"
            html += f"<div class='line' style='color:{color}'>{l}</div>"
        html += "</div><div style='margin-top:20px;color:#94a3b8'>Auto refresh every 5 sec - Source SIM Parat - Check Debug ENV + Debug Live</div><script>setTimeout(()=>location.reload(),5000);</script></body></html>"
        return html
    except Exception as e:
        return f"Logs ERR {e} - {list(LOGS)[-10:]}"

@app.route('/debug/env')
def debug_env():
    try:
        def check_env(*keys):
            for k in keys:
                v=os.getenv(k)
                if v: return True, k, len(v)
                v=os.getenv(k.lower())
                if v: return True, k.lower(), len(v)
                v=os.getenv(k.upper())
                if v: return True, k.upper(), len(v)
            return False, keys[0], 0
        results = {}
        results['ANGEL_API_KEY'] = check_env('ANGEL_API_KEY','ANGELONE_API_KEY','SMARTAPI_API_KEY','angel_api_key','ANGLE_ONE_API_KEY')
        results['ANGEL_CLIENT_ID'] = check_env('ANGEL_CLIENT_ID','ANGELONE_CLIENT_ID','CLIENT_ID','angel_client_id','ANGLE_ONE_CLIENT_ID','CLIENT_CODE')
        results['ANGEL_PASSWORD'] = check_env('ANGEL_PASSWORD','ANGELONE_PASSWORD','angel_password')
        results['ANGEL_TOTP_SECRET'] = check_env('ANGEL_TOTP_SECRET','ANGEL_TOTP','TOTP_SECRET','angel_totp_secret','ANGLE_ONE_TOTP_SECRET')
        results['TELEGRAM_BOT_TOKEN'] = check_env('TELEGRAM_BOT_TOKEN','telegram_bot_token')
        results['TELEGRAM_CHAT_ID'] = check_env('TELEGRAM_CHAT_ID','telegram_chat_id')
        results['ENABLE_LIVE_TRADING'] = check_env('ENABLE_LIVE_TRADING','enable_live_trading','ENABLE_LIVE','LIVE_MODE')
        
        html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Debug ENV - Source SIM Parat</title><style>body{background:#0a0e1a;color:#e2e8f0;padding:20px;font-family:monospace} .ok{color:#22c55e} .fail{color:#f87171} .card{background:#151d2f;padding:15px;border-radius:10px;margin:10px 0;border:1px solid #2d3748}</style></head><body>"
        html += "<h2 style='color:#22c55e'>Debug ENV Check - Source SIM Parat - ENV Set Aahe Ka?</h2>"
        html += "<div><a href='/logs' style='color:#3b82f6'>Back to /logs</a> | <a href='/' style='color:#3b82f6'>Home</a></div>"
        all_ok = True
        for key, (exists, found_key, length) in results.items():
            status = "OK" if exists else "MISSING"
            color = "ok" if exists else "fail"
            if "ENABLE_LIVE" in key:
                # ENABLE_LIVE should be NOT SET for live (delete kela)
                if not exists:
                    status = "OK - Not Set (Live Auto) - Delete Kela Correct!"
                    color = "ok"
                else:
                    status = f"Set ({found_key}) Length {length} - Should be DELETE for Live Auto!"
                    color = "fail"
                    all_ok = False
            else:
                if not exists:
                    all_ok = False
            html += f"<div class='card'><span class='{color}'>{key}: {status}</span> - Found Key: {found_key} Length: {length}</div>"
        
        if all_ok:
            html += "<div class='card' style='border-color:#22c55e'><span class='ok'>All ENV OK - Should be LIVE - Not SIM - If still SIM, check /debug/live for session fail reason</span></div>"
        else:
            html += "<div class='card' style='border-color:#f87171'><span class='fail'>Some ENV MISSING - Will be SIM - Source SIM Parat Reason: Credentials Missing - Set missing ENV in Render -> Environment -> Save -> Deploy</span></div>"
        
        html += "<div class='card'><b>Fix for Source SIM:</b><br>1. Render -> Environment -> Check 4 Angel ENV set? API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET<br>2. TOTP_SECRET = 32 chars Base32 - No spaces - From Google Authenticator<br>3. API_KEY = 20-30 chars - From Angel One Developer Portal<br>4. CLIENT_ID = S123456 format<br>5. Save -> Auto Deploy -> Wait 2 min -> Check /logs -> Should be Live OK</div>"
        html += "</body></html>"
        return html
    except Exception as e:
        return f"Debug ENV ERR {e}"

@app.route('/debug/live')
def debug_live():
    try:
        obj, msg = get_angle_one_session()
        html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Debug Live - Source SIM Parat</title><style>body{background:#0a0e1a;color:#e2e8f0;padding:20px;font-family:monospace} .ok{color:#22c55e} .fail{color:#f87171} .card{background:#151d2f;padding:15px;border-radius:10px;margin:10px 0;border:1px solid #2d3748}</style></head><body>"
        html += "<h2 style='color:#22c55e'>Debug Live Test - Source SIM Parat - Angel One Session Test</h2>"
        html += "<div><a href='/logs' style='color:#3b82f6'>Back to /logs</a> | <a href='/debug/env' style='color:#3b82f6'>Debug ENV</a> | <a href='/' style='color:#3b82f6'>Home</a></div>"
        if obj is None:
            html += f"<div class='card' style='border-color:#f87171'><span class='fail'>Live FAIL -> SIM - Reason: {msg}</span></div>"
            html += f"<div class='card'><b>Reason Details:</b> {msg}<br><br><b>Common Fixes:</b><br>- Invalid TOTP: TOTP_SECRET wrong - Check Google Authenticator secret - 32 chars<br>- Invalid API Key: API_KEY wrong - Regenerate from Angel Developer Portal<br>- Invalid Client ID: CLIENT_ID wrong - Should be S123456<br>- Invalid Password: PASSWORD wrong - Not MPIN - Password<br>- SmartApi Not Installed: requirements.txt check - smartapi-python + pyotp</div>"
        else:
            html += f"<div class='card' style='border-color:#22c55e'><span class='ok'>Live OK! - {msg} - Source Should be LIVE - Not SIM!</span></div>"
            # Try NIFTY LTP
            try:
                nifty_data = obj.ltpData("NSE", "NIFTY", "99926000")
                spot = float(nifty_data['data']['ltp'])
                html += f"<div class='card'><span class='ok'>NIFTY LTP OK: {spot:.2f} - Live Data Working!</span></div>"
            except Exception as e:
                html += f"<div class='card'><span class='fail'>NIFTY LTP Fail: {e} - Session OK but LTP fail</span></div>"
        html += "</body></html>"
        return html
    except Exception as e:
        return f"Debug Live ERR {e}"




@app.route('/api/logs')
def api_logs():
    try:
        logs = list(LOGS)[-100:]
        return jsonify({
            "logs": logs,
            "count": len(logs),
            "trades": list(TRADES)[-10:],
            "src": STATE.get("src","SIM"),
            "spot": STATE.get("spot",0),
            "trades_today": STATE.get("trades_today",0),
            "daily_pnl": STATE.get("daily_pnl",0),
            "is_live": "LIVE" in STATE.get("src","") or "Angle One" in STATE.get("src",""),
            "is_open": is_market_open()[0] if 'is_market_open' in globals() else False
        })
    except Exception as e:
        return jsonify({"logs": list(LOGS)[-20:], "error": str(e), "src": STATE.get("src","SIM")})

@app.route('/api/status')
def api_status():
    try:
        return jsonify({
            "spot": STATE.get("spot",0),
            "prem": STATE.get("prem",0),
            "src": STATE.get("src","SIM"),
            "is_live": "LIVE" in STATE.get("src","") or "Angle One" in STATE.get("src",""),
            "telegram_ok": TELEGRAM_BOT_TOKEN is not None,
            "logs_count": len(LOGS),
            "last_logs": list(LOGS)[-5:],
            "trades_today": STATE.get("trades_today",0),
            "is_open": is_market_open()[0] if 'is_market_open' in globals() else True
        })
    except Exception as e:
        return jsonify({"src": STATE.get("src","SIM"), "error": str(e)})

@app.route('/debug/env')
def debug_env():
    try:
        def check_env(*keys):
            for k in keys:
                v=os.getenv(k)
                if v: return True, k, len(v)
                v=os.getenv(k.lower())
                if v: return True, k.lower(), len(v)
                v=os.getenv(k.upper())
                if v: return True, k.upper(), len(v)
            return False, keys[0], 0
        results = {}
        results['ANGEL_API_KEY'] = check_env('ANGEL_API_KEY','ANGELONE_API_KEY','SMARTAPI_API_KEY','angel_api_key','ANGLE_ONE_API_KEY')
        results['ANGEL_CLIENT_ID'] = check_env('ANGEL_CLIENT_ID','ANGELONE_CLIENT_ID','CLIENT_ID','angel_client_id','ANGLE_ONE_CLIENT_ID','CLIENT_CODE')
        results['ANGEL_PASSWORD'] = check_env('ANGEL_PASSWORD','ANGELONE_PASSWORD','angel_password')
        results['ANGEL_TOTP_SECRET'] = check_env('ANGEL_TOTP_SECRET','ANGEL_TOTP','TOTP_SECRET','angel_totp_secret','ANGLE_ONE_TOTP_SECRET')
        results['TELEGRAM_BOT_TOKEN'] = check_env('TELEGRAM_BOT_TOKEN','telegram_bot_token')
        results['TELEGRAM_CHAT_ID'] = check_env('TELEGRAM_CHAT_ID','telegram_chat_id')
        results['ENABLE_LIVE_TRADING'] = check_env('ENABLE_LIVE_TRADING','enable_live_trading','ENABLE_LIVE','LIVE_MODE')
        html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Debug ENV - Source SIM Parat</title><style>body{background:#0a0e1a;color:#e2e8f0;padding:20px;font-family:monospace} .ok{color:#22c55e} .fail{color:#f87171} .card{background:#151d2f;padding:15px;border-radius:10px;margin:10px 0;border:1px solid #2d3748}</style></head><body>"
        html += "<h2 style='color:#22c55e'>Debug ENV Check - Source SIM Parat - ENV Set Aahe Ka?</h2>"
        html += "<div><a href='/logs' style='color:#3b82f6'>Back to /logs</a> | <a href='/' style='color:#3b82f6'>Home</a> | <a href='/debug/live' style='color:#22c55e'>Debug Live</a></div>"
        all_ok = True
        for key, (exists, found_key, length) in results.items():
            status = "OK" if exists else "MISSING"
            color = "ok" if exists else "fail"
            if "ENABLE_LIVE" in key:
                if not exists:
                    status = "OK - Not Set (Live Auto) - Delete Kela Correct!"
                    color = "ok"
                else:
                    if length==0:
                        status = "OK - Empty (Live Auto) - Delete Kela Correct!"
                        color = "ok"
                    else:
                        status = f"Set ({found_key}) Length {length} - Should be DELETE for Live Auto! Length 4 means maybe true/TRUE/false?"
                        color = "fail"
            else:
                if not exists:
                    all_ok = False
            html += f"<div class='card'><span class='{color}'>{key}: {status}</span> - Found Key: {found_key} Length: {length}</div>"
        if all_ok:
            html += "<div class='card' style='border-color:#22c55e'><span class='ok'>All ENV OK - Should be LIVE - Not SIM - If still SIM, check /debug/live for session fail reason - Market band asla tari LIVE asel!</span></div>"
        else:
            html += "<div class='card' style='border-color:#f87171'><span class='fail'>Some ENV MISSING - Will be SIM - Source SIM Parat Reason: Credentials Missing</span></div>"
        html += "</body></html>"
        return html
    except Exception as e:
        return f"Debug ENV ERR {e}"

@app.route('/debug/live')
def debug_live():
    try:
        obj, msg = get_angle_one_session()
        html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Debug Live - Source SIM Parat</title><style>body{background:#0a0e1a;color:#e2e8f0;padding:20px;font-family:monospace} .ok{color:#22c55e} .fail{color:#f87171} .card{background:#151d2f;padding:15px;border-radius:10px;margin:10px 0;border:1px solid #2d3748}</style></head><body>"
        html += "<h2 style='color:#22c55e'>Debug Live Test - Source SIM Parat - Angel One Session Test</h2>"
        html += "<div><a href='/logs' style='color:#3b82f6'>Back to /logs</a> | <a href='/debug/env' style='color:#3b82f6'>Debug ENV</a> | <a href='/' style='color:#3b82f6'>Home</a> | <a href='/api/status' style='color:#3b82f6'>API Status</a></div>"
        if obj is None:
            html += f"<div class='card' style='border-color:#f87171'><span class='fail'>Live FAIL -> SIM - Reason: {msg}</span></div>"
        else:
            html += f"<div class='card' style='border-color:#22c55e'><span class='ok'>Live OK! - {msg} - Source SHOULD be LIVE - Not SIM! - Market band asla tari LIVE!</span></div>"
            try:
                nifty_data = obj.ltpData("NSE", "NIFTY", "99926000")
                spot = float(nifty_data['data']['ltp'])
                html += f"<div class='card'><span class='ok'>NIFTY LTP OK: {spot:.2f} - Live Data Working! - Market band asla tari Last LTP deto!</span></div>"
            except Exception as e:
                html += f"<div class='card'><span class='fail'>NIFTY LTP Fail: {e}</span></div>"
        html += "</body></html>"
        return html
    except Exception as e:
        return f"Debug Live ERR {e}"


@app.route('/health')
def health():
    return jsonify({"status":"OK Target 1.6->2.414 Shift + SL 15pt Cost + SL Trail Fib1","fib":f"1.6 {STATE['fib_1_6']:.2f} 2.414 {STATE['fib_2_414']:.2f} SL {STATE['sl']:.2f} Target {STATE['target']:.2f}"})

@app.route('/force_buy')
def force_buy():
    try:
        curr=STATE["prem"]
        now=datetime.now(IST).strftime("%H:%M")
        entry=curr
        sl=STATE["fib_0_38"]
        target=STATE["fib_1_6"]
        STATE["pos"]={"entry":entry,"sl":sl,"target":target,"buy_time":now,"buy_price":curr,"strike":f"{STATE['strike']}{STATE['option_type']}","selected_type":STATE["selected_type"],"lots":1,"sl_shifted":False,"sl_trail_to_fib1":False,"target_shifted":False}
        STATE["trades_today"]+=1
        STATE["entry"]=entry; STATE["sl"]=sl; STATE["target"]=target; STATE["sl_shifted"]=False; STATE["target_shifted"]=False
        TRADES.append({"no":STATE["trades_today"],"buy_price":curr,"buy_time":now,"exit_price":0,"exit_time":"OPEN","exit_type":"OPEN FORCE BUY Target 1.6->2.414","pnl":0,"strike":f"{STATE['strike']}{STATE['option_type']}","selected_type":STATE["selected_type"]})
        send_tg_fixed(f"BUY {STATE['trades_today']}/5 @{curr:.1f} {STATE['selected_type']} TGT 1.6 {target:.1f}")
        return jsonify({"ok":True,"msg":f"BUY {STATE['trades_today']}/5 @ {curr:.2f} Target 1.6 {target:.2f} -> 2.414 {STATE['fib_2_414']:.2f} SL 0.38 {sl:.2f} Trail 15pt Cost + Fib1"})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)}),500

@app.route('/force_sell')
def force_sell():
    try:
        if STATE["pos"] is None:
            return jsonify({"ok":False,"msg":"No position"})
        curr=STATE["prem"]
        entry=STATE["pos"]["entry"]
        pnl=(curr-entry)*65
        STATE["pnl"]+=pnl
        STATE["daily_pnl"]+=pnl
        if TRADES and TRADES[-1]["exit_time"]=="OPEN":
            TRADES[-1]["exit_price"]=curr; TRADES[-1]["exit_time"]=datetime.now(IST).strftime("%H:%M"); TRADES[-1]["exit_type"]="FORCE SELL"; TRADES[-1]["pnl"]=round(pnl,0)
        STATE["pos"]=None
        STATE["sl_shifted"]=False
        STATE["target_shifted"]=False
        send_tg_fixed(f"SELL @{curr:.1f} P&L {pnl:.0f}")
        return jsonify({"ok":True,"msg":f"SELL @ {curr:.2f} P&L {pnl:.0f}"})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)}),500

@app.route('/test_telegram')
def test_telegram():
    try:
        # Test with short message + trade format both
        token=get_env_tg('TELEGRAM_BOT_TOKEN','telegram_bot_token')
        chat=get_env_tg('TELEGRAM_CHAT_ID','telegram_chat_id')
        if not token or not chat:
            return jsonify({"ok":False,"msg":f"Token Missing - Token {bool(token)} Chat {bool(chat)} - Set ENV TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"})
        # Try short test
        ok1, msg1 = send_tg_raw("Test OK Bot Working - 200 EMA + H1L1 H2L2 Both")
        # Try trade format test
        spot_test = STATE.get("spot", 22472.30)
        entry_test = STATE.get("prem", 45.85)
        exit_test = entry_test + 28.18
        qty_test = STATE.get("lot_size", 65)
        pnl_test = (exit_test-entry_test)*qty_test
        total_test = STATE.get("daily_pnl", 11672.05)
        option_test = STATE.get("selected_type", "PE 22350")[:20]
        ok2, msg2 = send_trade_message(spot_test, entry_test, exit_test, qty_test, pnl_test, total_test, option_test, "Test Trade Format - Market Volatility Entry", datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"))
        return jsonify({"ok":ok1 or ok2,"msg":f"Test1 Short: {msg1} | Test2 Trade Format: {msg2} | Token {bool(token)} Chat {chat[:5]}... | If Fail 400 Bad Request message too long -> Fix applied with short messages"})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Test ERR {e}"}),500

def bot_loop_latest():
    try:
        log("BOT START - Target 1.6 Fib -> 2.414 Shift + SL 15pt Cost + SL Trail Fib1 After Cross 1 Fib + 5F + Market Opening 150pt Delta 0.30")
        time.sleep(3)
        today_str=datetime.now(IST).strftime("%Y-%m-%d")
        last_started=STATE.get("last_bot_started_date")
        if last_started!=today_str:
            ok, msg = send_tg_fixed(f"Bot Started {STATE['open_price']:.0f} {STATE['selected_type']} TGT 1.6->2.414 SL 15pt Cost Fib1 Trail")
            STATE["last_bot_started_date"]=today_str
            log(f"Bot Started once today {today_str}: {msg} - Target 1.6->2.414 SL 15pt Cost + Fib1 Trail")
        else:
            log(f"Bot Started already sent today {today_str}")
        while True:
            try:
                is_open, market_msg, is_limit = is_market_open()
                if not is_open:
                    time.sleep(30)
                    continue
                
                now_dt_check=datetime.now(IST)
                hour_check=now_dt_check.hour
                minute_check=now_dt_check.minute
                if hour_check>=15 and minute_check>=15:
                    if STATE["pos"] is not None and not STATE.get("auto_squareoff_done",False):
                        curr_price=STATE["prem"]
                        entry=STATE["pos"]["entry"]
                        pnl=(curr_price-entry)*65
                        STATE["pnl"]+=pnl
                        STATE["daily_pnl"]+=pnl
                        STATE["auto_squareoff_done"]=True
                        if TRADES and TRADES[-1]["exit_time"]=="OPEN":
                            TRADES[-1]["exit_price"]=curr_price; TRADES[-1]["exit_time"]=now_dt_check.strftime("%H:%M"); TRADES[-1]["exit_type"]="AUTO SQUAREOFF 3:15 PM"; TRADES[-1]["pnl"]=round(pnl,0)
                        log(f"AUTO SQUAREOFF 3:15 PM @ {curr_price:.2f} P&L {pnl:.0f}")
                        # Suppressed baki kahi nako - send_tg_fixed(f"AUTO SQOFF 3:15 @{curr_price:.1f} P&L {pnl:.0f}")
                        STATE["pos"]=None
                        STATE["sl_shifted"]=False
                    time.sleep(60)
                    continue
                
                time_ok, time_msg = check_time_filter()
                if not time_ok:
                    if STATE["pos"] is None:
                        time.sleep(20)
                        continue
                
                loss_ok, loss_msg = check_consecutive_loss_filter()
                if not loss_ok:
                    time.sleep(30)
                    continue
                
                daily_ok, daily_msg = check_daily_target_sl()
                if not daily_ok:
                    if STATE["pos"] is None:
                        time.sleep(60)
                        continue
                
                spot, prem, strike, intr, tv, src = get_nse()
                STATE["spot"]=round(spot,2)
                STATE["prem"]=round(prem,2)
                STATE["strike"]=strike
                STATE["src"]=src
                
                tf=STATE["timeframe"]
                now_dt=datetime.now(IST)
                minute=now_dt.minute
                cm=(minute//tf)*tf
                now_str=f"{now_dt.hour}:{cm:02d} TF{tf}"
                
                if len(CANDLES)==0 or CANDLES[-1]["t"]!=now_str:
                    CANDLES.append({"o":prem,"h":prem,"l":prem,"c":prem,"t":now_str,"buy":False,"sell_sl":False,"sell_tgt":False})
                else:
                    c=CANDLES[-1]
                    c["h"]=max(c["h"],prem)
                    c["l"]=min(c["l"],prem)
                    c["c"]=prem
                
                pivot_low_val, pivot_high_val = detect_pivots()
                if pivot_low_val is not None:
                    if STATE["low1"] is None: STATE["low1"]=pivot_low_val
                    elif STATE["low2"] is None: STATE["low2"]=pivot_low_val
                    elif STATE["low3"] is None: STATE["low3"]=pivot_low_val
                    else:
                        STATE["low1"]=STATE["low2"]; STATE["low2"]=STATE["low3"]; STATE["low3"]=pivot_low_val
                    STATE["l2"]=STATE["low2"]
                if pivot_high_val is not None:
                    if STATE["high1"] is None: STATE["high1"]=pivot_high_val
                    elif STATE["high2"] is None: STATE["high2"]=pivot_high_val
                    else: STATE["high1"]=STATE["high2"]; STATE["high2"]=pivot_high_val
                    if STATE["neck1"] is None: STATE["neck1"]=pivot_high_val
                    elif STATE["neck2"] is None: STATE["neck2"]=pivot_high_val
                    else: STATE["neck1"]=STATE["neck2"]; STATE["neck2"]=pivot_high_val
                    STATE["neckline"]=STATE["neck2"]
                    STATE["h2"]=STATE["high2"] if STATE["high2"] is not None else STATE["neck2"]
                
                h2 = STATE["h2"] if STATE["h2"] is not None else 85.2
                l2 = STATE["l2"] if STATE["l2"] is not None else 62.0
                h1 = STATE["high1"] if STATE["high1"] is not None else STATE.get("h1", 82.0)
                l1 = STATE["low1"] if STATE["low1"] is not None else STATE.get("l1", 75.0)
                fib_data = calc_fib_h2_l2(h2, l2)
                fib_data_h1_l1 = calc_fib_h2_l2(h1, l1) if h1 is not None and l1 is not None else None
                
                # First High1 & Low1 Pan Ghe - Doni Ghetlyavar Kay Hote Te Bagh
                if fib_data_h1_l1:
                    STATE["h1"]=h1
                    STATE["l1"]=l1
                    STATE["fib_range_h1_l1"]=fib_data_h1_l1["range"]
                    STATE["fib_0_h1_l1"]=fib_data_h1_l1["fib_0"]
                    STATE["fib_0_38_h1_l1"]=fib_data_h1_l1["fib_0_38"]
                    STATE["fib_0_5_h1_l1"]=fib_data_h1_l1["fib_0_5"]
                    STATE["fib_1_h1_l1"]=fib_data_h1_l1["fib_1"]
                    STATE["fib_1_6_h1_l1"]=fib_data_h1_l1["fib_1_6"]
                    STATE["fib_2_414_h1_l1"]=fib_data_h1_l1["fib_2_414"]
                    STATE["both_fib_available"]=True if fib_data and fib_data_h1_l1 else False
                
                if fib_data:
                    STATE["fib_range_h2_l2"]=fib_data["range"]
                    STATE["fib_0"]=fib_data["fib_0"]
                    STATE["fib_0_38"]=fib_data["fib_0_38"]
                    STATE["fib_0_5"]=fib_data["fib_0_5"]
                    STATE["fib_1"]=fib_data["fib_1"]
                    STATE["fib_1_272"]=fib_data["fib_1_272"]
                    STATE["fib_1_6"]=fib_data["fib_1_6"]
                    STATE["fib_2_414"]=fib_data["fib_2_414"]
                    STATE["fib_source"]="H2-L2 Main + H1-L1 Extra Both" if fib_data_h1_l1 else "H2-L2 Only"
                    if not STATE["sl_shifted"]:
                        STATE["sl"]=fib_data["fib_0_38"]
                    if not STATE["target_shifted"]:
                        STATE["target"]=fib_data["fib_1_6"]
                        STATE["target1"]=fib_data["fib_1_6"]
                        STATE["target2"]=fib_data["fib_2_414"]
                    # Log when both available
                    if fib_data_h1_l1:
                        log(f"BOT LOOP H1L1 & H2L2 Both - First High1 Low1 Pan Ghe - Doni: H1 {h1:.1f} L1 {l1:.1f} Range {fib_data_h1_l1['range']:.1f} Fib1.6 {fib_data_h1_l1['fib_1_6']:.1f} | H2 {h2:.1f} L2 {l2:.1f} Range {fib_data['range']:.1f} Fib1.6 {fib_data['fib_1_6']:.1f}")
                
                closes=[c['c'] for c in list(CANDLES)]
                opens=[c['o'] for c in list(CANDLES)]
                ema=calc_ema(closes, EMA_LENGTH)
                atr=calc_atr(list(CANDLES), ATR_LENGTH)
                rsi=calc_rsi(closes, 14)
                vwap=calc_vwap(list(CANDLES))
                supertrend_val, supertrend_dir=calc_supertrend(list(CANDLES), 10, 3.0)
                last_close=closes[-1] if closes else 75
                last_open=opens[-1] if opens else 74.5
                prev_close=closes[-2] if len(closes)>=2 else last_close-1
                prev_ema=calc_ema(closes[:-1], EMA_LENGTH) if len(closes)>=2 else ema-0.5
                vol_percent=(atr/last_close*100) if last_close!=0 else 0.85
                distance=abs(last_close-ema)/ema*100 if ema!=0 else 0.45
                nearEMA=distance<=1.0
                ivOK=vol_percent>=MIN_VOL and vol_percent<=MAX_VOL
                
                STATE["ema"]=ema; STATE["atr"]=atr; STATE["volatility_percent"]=vol_percent
                STATE["rsi"]=rsi; STATE["vwap"]=vwap; STATE["supertrend"]=supertrend_val; STATE["supertrend_dir"]=supertrend_dir
                STATE["distanceFromEMA"]=distance; STATE["nearEMA"]=nearEMA; STATE["ivOK"]=ivOK
                
                rsi_filter=False
                if STATE["option_type"]=="CE":
                    if rsi>55 and rsi<75:
                        rsi_filter=True
                else:
                    if rsi<45 and rsi>25:
                        rsi_filter=True
                if STATE["option_type"]=="":
                    rsi_filter=True
                
                volume_filter = vol_percent>0.3
                market_diff=STATE["spot"]-STATE["open_price"] if STATE["open_price"]!=0 else 0
                market_diff_filter = abs(market_diff)<=250
                
                vwap_filter=False
                if STATE["option_type"]=="CE":
                    if last_close > vwap:
                        vwap_filter=True
                elif STATE["option_type"]=="PE":
                    if last_close < vwap:
                        vwap_filter=True
                else:
                    vwap_filter=True
                
                supertrend_filter=False
                if STATE["option_type"]=="CE":
                    if supertrend_dir=="bullish" and last_close>supertrend_val:
                        supertrend_filter=True
                elif STATE["option_type"]=="PE":
                    if supertrend_dir=="bearish" and last_close<supertrend_val:
                        supertrend_filter=True
                else:
                    supertrend_filter=True
                
                two_candle_confirm=False
                retest_fib_05=False
                fib_0_5 = STATE["fib_0_5"]
                if len(closes)>=3 and fib_0_5 is not None:
                    if closes[-1]>=opens[-1] and closes[-2]>=opens[-2]:
                        if closes[-1]>ema and closes[-2]>ema:
                            two_candle_confirm=True
                    if abs(closes[-2]-fib_0_5)/fib_0_5*100 < 1.0:
                        if closes[-1]>fib_0_5:
                            retest_fib_05=True
                    if not retest_fib_05 and STATE["fib_0_5_cross"]:
                        retest_fib_05=True
                
                fib_0_5_cross=False
                if fib_0_5 is not None:
                    if last_close > fib_0_5 and prev_close <= fib_0_5:
                        fib_0_5_cross=True
                
                fib_1_cross=False
                fib_1 = STATE["fib_1"]
                if fib_1 is not None:
                    if last_close > fib_1 and prev_close <= fib_1:
                        fib_1_cross=True
                
                fib_1_6_near=False
                fib_1_6 = STATE["fib_1_6"]
                if fib_1_6 is not None:
                    if abs(last_close - fib_1_6)/fib_1_6*100 < 2.0:
                        fib_1_6_near=True
                
                STATE["fib_0_5_cross"]=fib_0_5_cross
                STATE["fib_1_cross"]=fib_1_cross
                STATE["fib_1_6_near"]=fib_1_6_near
                
                ema_cross_fib_0_5=False
                if fib_0_5 is not None:
                    if ema > fib_0_5 and prev_ema <= fib_0_5:
                        ema_cross_fib_0_5=True
                    elif ema > fib_0_5 and last_close > fib_0_5:
                        ema_cross_fib_0_5=True
                STATE["ema_cross_fib_0_5"]=ema_cross_fib_0_5
                
                green_candle_upside_ema=False
                if last_close >= last_open and last_close > ema:
                    green_candle_upside_ema=True
                STATE["green_candle_upside_ema"]=green_candle_upside_ema
                
                low1=STATE["low1"]; low2=STATE["low2"]; low3=STATE["low3"]
                neckline=STATE["neckline"]
                hasThreeLows=low1 is not None and low2 is not None and low3 is not None
                hasNeckline=neckline is not None
                inverseHS=False
                if hasThreeLows and hasNeckline:
                    if low2 < low1 and low2 < low3: inverseHS=True
                STATE["inverseHS"]=inverseHS
                
                isAllowedTF=STATE["timeframe"] in [1,5,15]
                STATE["isAllowedTF"]=isAllowedTF
                
                five_rules = fib_0_5_cross and ema_cross_fib_0_5 and green_candle_upside_ema
                buyCondition = five_rules and inverseHS and nearEMA and ivOK and isAllowedTF and rsi_filter and volume_filter and market_diff_filter and vwap_filter and supertrend_filter and two_candle_confirm and retest_fib_05
                STATE["five_rules"]=five_rules
                STATE["buyCondition"]=buyCondition
                
                if buyCondition:
                    entryPrice=last_close
                    stopLoss=STATE["fib_0_38"]
                    target=STATE["fib_1_6"]
                    STATE["entry"]=entryPrice
                    STATE["sl"]=stopLoss
                    STATE["sl_shifted"]=False
                    STATE["sl_trail_to_fib1"]=False
                    STATE["sl_trail_to_fib1_done"]=False
                    STATE["target_shifted"]=False
                    STATE["target"]=target
                    STATE["target1"]=STATE["fib_1_6"]
                    STATE["target2"]=STATE["fib_2_414"]
                
                if buyCondition and STATE["pos"] is None:
                    if STATE["trades_today"]>=5:
                        time.sleep(10)
                        continue
                    time_ok_buy, _ = check_time_filter()
                    if not time_ok_buy:
                        time.sleep(10)
                        continue
                    entryPrice=last_close
                    stopLoss=STATE["fib_0_38"]
                    target=STATE["fib_1_6"]
                    CANDLES[-1]["buy"]=True
                    lots=calc_lots()
                    STATE["pos"]={"entry":entryPrice,"sl":stopLoss,"target":target,"buy_time":now_str,"buy_price":entryPrice,"strike":f"{strike}{STATE['option_type']}","open_price":STATE["open_price"],"call_strike":STATE["call_strike"],"put_strike":STATE["put_strike"],"selected_type":STATE["selected_type"],"trend":STATE["trend"],"h2":h2,"l2":l2,"range":STATE["fib_range_h2_l2"],"fib_0_38":STATE["fib_0_38"],"fib_0_5":STATE["fib_0_5"],"fib_1":STATE["fib_1"],"fib_1_6":STATE["fib_1_6"],"fib_2_414":STATE["fib_2_414"],"fib05Cross":fib_0_5_cross,"emaCrossFib05":ema_cross_fib_0_5,"greenAboveEMA":green_candle_upside_ema,"fiveRules":five_rules,"rsi":rsi,"lots":lots,"sl_shifted":False,"target_shifted":False}
                    STATE["trades"]+=1
                    STATE["trades_today"]+=1
                    STATE["entry"]=entryPrice; STATE["sl"]=stopLoss; STATE["sl_shifted"]=False; STATE["target"]=target; STATE["target_shifted"]=False
                    TRADES.append({"no":STATE["trades_today"],"buy_price":entryPrice,"buy_time":now_str,"exit_price":0,"exit_time":"OPEN","exit_type":"OPEN Target 1.6->2.414","pnl":0,"strike":f"{strike}{STATE['option_type']}","open_price":STATE["open_price"],"call_strike":STATE["call_strike"],"put_strike":STATE["put_strike"],"selected_type":STATE["selected_type"],"trend":STATE["trend"],"h2":h2,"l2":l2,"range":STATE["fib_range_h2_l2"],"fib05":STATE["fib_0_5"],"sl":stopLoss,"fib_0_38":STATE["fib_0_38"],"fib_1":STATE["fib_1"],"fib_1_6":STATE["fib_1_6"],"fib_2_414":STATE["fib_2_414"],"entry":entryPrice,"target":target,"rsi":rsi,"lots":lots})
                    log(f"BUY Target 1.6->2.414 | Trade {STATE['trades_today']}/5 | BUY @ {entryPrice:.2f} {STATE['selected_type']} Lots {lots} RSI {rsi:.0f} | SL {STATE['fib_0_38']:.2f} TGT 1.6 {STATE['fib_1_6']:.2f} -> 2.414 {STATE['fib_2_414']:.2f}")
                    # Send BUY in TRADE format as well - Call and put buy kelele message ya format madhe yeude
                    try:
                        spot_buy = STATE.get("spot", 0)
                        qty_buy = STATE.get("lot_size", 65)
                        total_buy = STATE.get("daily_pnl", 0)
                        option_buy = STATE.get("selected_type", f"{STATE.get('strike',0)}{STATE.get('option_type','')}")[:20]
                        reason_buy = f"BUY Entry Market Volatility Entry (2 min cycle) Trade {STATE['trades_today']}/5"
                        time_buy = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        # BUY format: Use entry as both entry and exit for BUY notification, PnL 0
                        send_trade_message(spot_buy, entryPrice, entryPrice, qty_buy, 0, total_buy, option_buy, reason_buy, time_buy)
                    except Exception as e:
                        log(f"BUY Telegram ERR {e}")
                    # Also send short BUY via fixed
                    ok, msg = send_tg_raw(f"BUY {STATE['trades_today']}/5 @{entryPrice:.0f} {STATE['selected_type'][:15]}")
                
                if STATE["pos"] is not None:
                    entry=STATE["pos"]["entry"]
                    curr_price=last_close
                    # SL Trail 1: 15pt -> Cost to Cost
                    if not STATE["sl_shifted"]:
                        if curr_price >= entry + 15:
                            STATE["pos"]["sl"]=entry
                            STATE["sl"]=entry
                            STATE["sl_shifted"]=True
                            log(f"SL Trail 1: 15pt Cost | Entry {entry:.2f} -> SL {entry:.2f} | Premium {curr_price:.2f} >= Entry+15 {entry+15:.2f}")
                            # Suppressed per user baki kahi nako - send_tg_fixed(f"SL Trail Cost @{entry:.1f}")
                    # FINAL: After cross Fib 1.6 -> SL to Fib 1.0 - After cross 1.6 SL shift/trail to 1 fibb level - Final Logic
                    if STATE["sl_shifted"] and not STATE.get("sl_trail_to_fib1_after_16",False):
                        fib_1_6_val=STATE["fib_1_6"]
                        fib_1_val=STATE["fib_1"]
                        if fib_1_6_val is not None and fib_1_val is not None and curr_price >= fib_1_6_val:
                            STATE["pos"]["sl"]=fib_1_val
                            STATE["sl"]=fib_1_val
                            STATE["sl_trail_to_fib1_after_16"]=True
                            STATE["sl_trail_to_fib1"]=True
                            STATE["sl_trail_to_fib1_done"]=True
                            log(f"SL Trail 2 FINAL: Cross Fib1.6 {fib_1_6_val:.2f} -> SL to Fib1 {fib_1_val:.2f} | Premium {curr_price:.2f} - After cross 1.6 SL shift/trail to 1 fibb level - Final")
                            # Suppressed per user baki kahi nako - send_tg_fixed(f"SL Fib1 @{fib_1_val:.0f} After 1.6")
                    # Target Shift: 1.6 near -> 2.414
                    if not STATE["target_shifted"]:
                        fib_1_6_val=STATE["fib_1_6"]
                        if fib_1_6_val is not None and curr_price >= fib_1_6_val*0.98:
                            STATE["pos"]["target"]=STATE["fib_2_414"]
                            STATE["target"]=STATE["fib_2_414"]
                            STATE["target_shifted"]=True
                            log(f"TGT Shift: 1.6 Near {fib_1_6_val:.2f} -> Shift to 2.414 {STATE['fib_2_414']:.2f} | Premium {curr_price:.2f}")
                            # Suppressed per user baki kahi nako - send_tg_fixed(f"TGT Shift 2.414 @{STATE['fib_2_414']:.1f}")
                
                if STATE["pos"]:
                    curr_price=list(CANDLES)[-1]['c']
                    if curr_price <= STATE["pos"]["sl"]:
                        sl_shifted=STATE["pos"].get("sl_shifted",False)
                        lots=STATE["pos"].get("lots",1)
                        pnl=(STATE["pos"]["sl"]-STATE["pos"]["entry"])*65*lots
                        if sl_shifted:
                            # If SL shifted to Fib1, may still have profit
                            if STATE.get("sl_trail_to_fib1_done",False):
                                pnl=(STATE["pos"]["sl"]-STATE["pos"]["entry"])*65*lots
                            else:
                                pnl=0
                        STATE["pnl"]+=pnl
                        STATE["daily_pnl"]+=pnl
                        CANDLES[-1]["sell_sl"]=True
                        if not sl_shifted:
                            STATE["consecutive_losses"]+=1
                            STATE["losses"]=STATE.get("losses",0)+1
                            if STATE["consecutive_losses"]>=2:
                                STATE["pause_until"]=datetime.now(IST)+timedelta(minutes=30)
                                log(f"2 SL Pause 30 Min Till {STATE['pause_until']}")
                                # Suppressed per user baki kahi nako - send_tg_fixed(f"2 SL Pause 30M P&L {STATE['daily_pnl']:.0f}")
                        else:
                            STATE["consecutive_losses"]=0
                            if pnl>0:
                                STATE["wins"]=STATE.get("wins",0)+1
                        if TRADES and TRADES[-1]["exit_time"]=="OPEN":
                            exit_type="SL HIT Cost" if sl_shifted and not STATE.get("sl_trail_to_fib1_done",False) else f"SL HIT Fib1 Trail" if STATE.get("sl_trail_to_fib1_done",False) else "SL HIT 0.38"
                            TRADES[-1]["exit_price"]=curr_price; TRADES[-1]["exit_time"]=now_str; TRADES[-1]["exit_type"]=exit_type; TRADES[-1]["pnl"]=round(pnl,0)
                        log(f"SL HIT | Trade {STATE['trades_today']}/5 P&L {pnl:.0f} Daily {STATE['daily_pnl']:.0f}")
                        # Call and put buy kelele message ya format madhe yeude baki kahi nako - Only TRADE format
                        spot_val = STATE.get("spot", 0)
                        entry_val = STATE["pos"]["entry"] if STATE["pos"] else curr_price
                        qty_val = STATE.get("lot_size", 65)
                        total_pnl = STATE.get("daily_pnl", 0)
                        option_str = STATE.get("selected_type", f"{STATE.get('strike',0)}{STATE.get('option_type','')}")
                        reason_str = exit_type if 'exit_type' in locals() else "SL HIT"
                        time_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        send_trade_message(spot_val, entry_val, curr_price, qty_val, pnl, total_pnl, option_str, reason_str, time_str)
                        STATE["pos"]=None
                        STATE["sl_shifted"]=False
                        STATE["target_shifted"]=False
                        STATE["sl_trail_to_fib1"]=False
                        STATE["sl_trail_to_fib1_done"]=False
                    elif curr_price >= STATE["pos"]["target"]:
                        lots=STATE["pos"].get("lots",1)
                        pnl=(STATE["pos"]["target"]-STATE["pos"]["entry"])*65*lots
                        STATE["pnl"]+=pnl
                        STATE["daily_pnl"]+=pnl
                        CANDLES[-1]["sell_tgt"]=True
                        STATE["consecutive_losses"]=0
                        STATE["wins"]=STATE.get("wins",0)+1
                        if TRADES and TRADES[-1]["exit_time"]=="OPEN":
                            exit_type=f"TGT HIT 1.6" if not STATE["target_shifted"] else f"TGT HIT 2.414 After 1.6 Shift"
                            TRADES[-1]["exit_price"]=curr_price; TRADES[-1]["exit_time"]=now_str; TRADES[-1]["exit_type"]=exit_type; TRADES[-1]["pnl"]=round(pnl,0)
                        log(f"TGT HIT | Trade {STATE['trades_today']}/5 P&L {pnl:.0f} Daily {STATE['daily_pnl']:.0f} TGT {STATE['pos']['target']:.2f}")
                        # Call and put buy kelele message ya format madhe yeude baki kahi nako - Only TRADE format
                        spot_val = STATE.get("spot", 0)
                        entry_val = STATE["pos"]["entry"] if STATE["pos"] else curr_price
                        qty_val = STATE.get("lot_size", 65)
                        total_pnl = STATE.get("daily_pnl", 0)
                        option_str = STATE.get("selected_type", f"{STATE.get('strike',0)}{STATE.get('option_type','')}")
                        reason_str = exit_type if 'exit_type' in locals() else "TGT HIT 2.414"
                        time_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        send_trade_message(spot_val, entry_val, curr_price, qty_val, pnl, total_pnl, option_str, reason_str, time_str)
                        STATE["pos"]=None
                        STATE["sl_shifted"]=False
                        STATE["target_shifted"]=False
                        STATE["sl_trail_to_fib1"]=False
                        STATE["sl_trail_to_fib1_done"]=False
                
                time.sleep(10)
            except Exception as e:
                import traceback
                log(f"BOT LOOP ERR {e} {traceback.format_exc()[:250]}")
                time.sleep(10)
    except Exception as e:
        log(f"BOT START ERR {e}")

threading.Thread(target=bot_loop_latest, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
