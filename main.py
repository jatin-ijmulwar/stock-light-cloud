import os
import time
import requests
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Load local .env file if it exists
load_dotenv()

# --- Configuration (from Environment Variables for cloud compatibility) ---
SMARTTHINGS_TOKEN = os.getenv("SMARTTHINGS_TOKEN", "")
DEVICE_ID = os.getenv("DEVICE_ID", "")

TICKER = os.getenv("TICKER", "TEMPSENS.NS")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30")) # Slower polling for cloud

MODE = os.getenv("MODE", "portfolio")
EXPECTED = float(os.getenv("EXPECTED", "600.00"))
STOP_LOSS = float(os.getenv("STOP_LOSS", "580.00"))
TARGET = float(os.getenv("TARGET", "630.00"))


# --- SmartThings Colors (Hue 0-100, Saturation 0-100) ---
# Note: SmartThings hue is usually 0-100 (percentage of 360 degrees)
COLOR_RED   = {"hue": 0, "saturation": 100}
COLOR_GREEN = {"hue": 33, "saturation": 100}
COLOR_BLUE  = {"hue": 66, "saturation": 100}


def set_bulb_color(color_dict):
    """Sends a request to the SmartThings API to change bulb color."""
    if SMARTTHINGS_TOKEN == "YOUR_TOKEN_HERE":
        print("Please set your SMARTTHINGS_TOKEN environment variable.")
        return

    url = f"https://api.smartthings.com/v1/devices/{DEVICE_ID}/commands"
    headers = {
        "Authorization": f"Bearer {SMARTTHINGS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "commands": [
            {
                "component": "main",
                "capability": "switch",
                "command": "on"
            },
            {
                "component": "main",
                "capability": "colorControl",
                "command": "setColor",
                "arguments": [color_dict]
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        print(f"SmartThings API Error: {e}")


def is_market_open():
    """Checks if the NSE market is currently open."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: # Saturday or Sunday
        return False
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_start <= now <= market_end


# Price cache
_price_cache = {"price": None, "time": 0}

def get_last_price(ticker: str) -> float:
    now = time.time()
    # Cache for a few seconds to prevent accidental spamming
    if _price_cache["price"] is not None and (now - _price_cache["time"]) < 3:
        return _price_cache["price"]
        
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            price = float(data['chart']['result'][0]['meta']['regularMarketPrice'])
            _price_cache["price"] = price
            _price_cache["time"] = now
            return price
    except Exception as e:
        print(f"Yahoo API Error: {e}")
        
    if _price_cache["price"] is not None:
        return _price_cache["price"]
    raise RuntimeError(f"Could not fetch price for {ticker}")


import asyncio
from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager

async def polling_loop():
    print(f"Starting Cloud Polling for {TICKER}...")
    prev_price = None
    sl_triggered = False
    tgt_triggered = False
    
    while True:
        try:
            if not is_market_open():
                print("Market is closed. Sleeping for 60 seconds...")
                await asyncio.sleep(60)
                continue
                
            price = get_last_price(TICKER)
            now_str = datetime.now().strftime("%H:%M:%S")
            
            # --- Alerts ---
            if price <= STOP_LOSS:
                if not sl_triggered:
                    print(f"[{now_str}] 🚨 STOP LOSS HIT! Setting bulb to RED.")
                    set_bulb_color(COLOR_RED)
                    sl_triggered = True
                await asyncio.sleep(POLL_SECONDS)
                continue
                
            if price >= TARGET:
                if not tgt_triggered:
                    print(f"[{now_str}] 🎯 TARGET HIT! Setting bulb to GREEN.")
                    set_bulb_color(COLOR_GREEN)
                    tgt_triggered = True
                await asyncio.sleep(POLL_SECONDS)
                continue
                
            # Reset triggers if we are back in the safe zone
            if price > STOP_LOSS: sl_triggered = False
            if price < TARGET: tgt_triggered = False
            
            # --- Normal Mode ---
            if MODE == "portfolio":
                diff = price - EXPECTED
            else: # tick mode
                diff = price - (prev_price if prev_price else price)
                
            if diff > 0:
                print(f"[{now_str}] {TICKER}: ₹{price:.2f} (UP). Setting Green.")
                set_bulb_color(COLOR_GREEN)
            elif diff < 0:
                print(f"[{now_str}] {TICKER}: ₹{price:.2f} (DOWN). Setting Red.")
                set_bulb_color(COLOR_RED)
            else:
                if prev_price is None:
                    print(f"[{now_str}] {TICKER}: ₹{price:.2f}. Setting Blue.")
                    set_bulb_color(COLOR_BLUE)
                    
            prev_price = price
            
        except Exception as e:
            print(f"Loop Error: {e}")
            
        await asyncio.sleep(POLL_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the polling loop in the background when the server starts
    task = asyncio.create_task(polling_loop())
    yield
    # Cancel the task when the server shuts down
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health_check():
    return {"status": "running", "ticker": TICKER, "mode": MODE}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
