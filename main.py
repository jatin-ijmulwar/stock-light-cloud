import os
import time
import requests
import asyncio
from datetime import datetime
import pytz
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load local .env file if it exists
load_dotenv()

# --- Secrets ---
SMARTTHINGS_TOKEN = os.getenv("SMARTTHINGS_TOKEN", "")
DEVICE_ID = os.getenv("DEVICE_ID", "")

# --- Dynamic Configuration (Defaults from Env Vars) ---
config = {
    "ticker": os.getenv("TICKER", "TEMPSENS.NS"),
    "poll_seconds": int(os.getenv("POLL_SECONDS", "30")), # Slower polling for cloud
    "mode": os.getenv("MODE", "portfolio"),
    "expected": float(os.getenv("EXPECTED", "600.00")),
    "stop_loss": float(os.getenv("STOP_LOSS", "580.00")),
    "target": float(os.getenv("TARGET", "630.00"))
}

# --- State ---
state = {
    "market_status": "UNKNOWN",
    "last_price": None,
    "last_update": None
}

class ConfigModel(BaseModel):
    ticker: str
    poll_seconds: int
    mode: str
    expected: float
    stop_loss: float
    target: float

# --- SmartThings Colors ---
COLOR_RED   = {"hue": 0, "saturation": 100}
COLOR_GREEN = {"hue": 33, "saturation": 100}
COLOR_BLUE  = {"hue": 66, "saturation": 100}

def set_bulb_color(color_dict):
    if not SMARTTHINGS_TOKEN or not DEVICE_ID:
        print("SmartThings Token or Device ID is missing!")
        return

    url = f"https://api.smartthings.com/v1/devices/{DEVICE_ID}/commands"
    headers = {
        "Authorization": f"Bearer {SMARTTHINGS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "commands": [
            {"component": "main", "capability": "switch", "command": "on"},
            {"component": "main", "capability": "colorControl", "command": "setColor", "arguments": [color_dict]}
        ]
    }
    
    try:
        requests.post(url, headers=headers, json=payload, timeout=5)
    except Exception as e:
        print(f"SmartThings API Error: {e}")

def is_market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_start <= now <= market_end

_price_cache = {"price": None, "time": 0}

def get_last_price(ticker: str) -> float:
    now = time.time()
    if _price_cache["price"] is not None and (now - _price_cache["time"]) < 3:
        return _price_cache["price"]
        
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            price = float(response.json()['chart']['result'][0]['meta']['regularMarketPrice'])
            _price_cache["price"] = price
            _price_cache["time"] = now
            return price
    except Exception as e:
        print(f"Yahoo API Error: {e}")
        
    if _price_cache["price"] is not None:
        return _price_cache["price"]
    raise RuntimeError(f"Could not fetch price for {ticker}")

async def polling_loop():
    print("Starting Cloud Polling...")
    prev_price = None
    sl_triggered = False
    tgt_triggered = False
    
    while True:
        try:
            ticker = config["ticker"]
            poll_seconds = config["poll_seconds"]
            mode = config["mode"]
            expected = config["expected"]
            stop_loss = config["stop_loss"]
            target = config["target"]
            
            if not is_market_open():
                state["market_status"] = "CLOSED"
                await asyncio.sleep(60)
                continue
                
            state["market_status"] = "OPEN"
            price = get_last_price(ticker)
            now_str = datetime.now().strftime("%H:%M:%S")
            state["last_price"] = price
            state["last_update"] = now_str
            
            # --- Alerts ---
            if price <= stop_loss:
                if not sl_triggered:
                    print(f"[{now_str}] 🚨 STOP LOSS HIT! RED.")
                    set_bulb_color(COLOR_RED)
                    sl_triggered = True
                await asyncio.sleep(poll_seconds)
                continue
                
            if price >= target:
                if not tgt_triggered:
                    print(f"[{now_str}] 🎯 TARGET HIT! GREEN.")
                    set_bulb_color(COLOR_GREEN)
                    tgt_triggered = True
                await asyncio.sleep(poll_seconds)
                continue
                
            if price > stop_loss: sl_triggered = False
            if price < target: tgt_triggered = False
            
            # --- Normal Mode ---
            if mode == "portfolio":
                diff = price - expected
            else:
                diff = price - (prev_price if prev_price else price)
                
            if diff > 0:
                print(f"[{now_str}] {ticker}: ₹{price:.2f} (UP). Green.")
                set_bulb_color(COLOR_GREEN)
            elif diff < 0:
                print(f"[{now_str}] {ticker}: ₹{price:.2f} (DOWN). Red.")
                set_bulb_color(COLOR_RED)
            else:
                if prev_price is None:
                    print(f"[{now_str}] {ticker}: ₹{price:.2f}. Blue.")
                    set_bulb_color(COLOR_BLUE)
                    
            prev_price = price
            
        except Exception as e:
            print(f"Loop Error: {e}")
            
        await asyncio.sleep(config["poll_seconds"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(polling_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_ui():
    return FileResponse("static/index.html")

@app.get("/api/config")
def get_config():
    return config

@app.post("/api/config")
async def update_config(new_config: ConfigModel):
    global config
    config.update(new_config.model_dump())
    return {"status": "success", "config": config}

@app.get("/api/status")
def get_status():
    return state

@app.get("/api/search")
def search_stocks(q: str):
    if not q: return {"results": []}
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            quotes = response.json().get("quotes", [])
            results = [{"symbol": qt.get("symbol"), "name": qt.get("shortname", "")} for qt in quotes if qt.get("symbol")]
            return {"results": results}
    except Exception:
        pass
    return {"results": []}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
