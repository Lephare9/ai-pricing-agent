print("🔥 AI PRICING AGENT v6 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import io
import re
from statistics import median
from PIL import Image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# -------------------------
# 🖼️ BILLEDE KOMPRIMERING
# -------------------------
def compress_image(image_bytes, max_size=800):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_size, max_size))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)

        compressed = buf.getvalue()
        print(f"📦 COMPRESSED: {len(image_bytes)} → {len(compressed)} bytes")

        return compressed

    except Exception as e:
        print("❌ Compress fejl:", e)
        return image_bytes


# -------------------------
# 🤖 GEMINI ANALYSE (NO FALLBACK)
# -------------------------
def detect_object(image_bytes):
    try:
        import google.generativeai as genai

        if not GEMINI_API_KEY:
            raise Exception("GEMINI_API_KEY mangler")

        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-1.5-flash")

        response = model.generate_content([
            {"mime_type": "image/jpeg", "data": image_bytes},
            "Beskriv genstanden meget kort (1-3 ord på dansk)"
        ])

        text = response.text.strip().lower()
        print("🧠 GEMINI:", text)

        if not text or len(text) < 3:
            raise Exception("Tomt svar")

        return text

    except Exception as e:
        print("🚨 GEMINI FEJL:", e)
        return None


# -------------------------
# 🔍 PRISSØGNING
# -------------------------
def search_prices(query):
    try:
        print(f"🔎 SEARCH: {query}")

        params = {
            "engine": "google",
            "q": f"site:dba.dk {query}",
            "api_key": SERPAPI_KEY,
            "gl": "dk",
            "hl": "da"
        }

        res = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data = res.json()

        prices = []

        for r in data.get("organic_results", []):
            snippet = (r.get("title", "") + " " + r.get("snippet", "")).lower()

            matches = re.findall(r'(\d[\d\.]{1,6})\s*(kr|,-)', snippet)

            for m in matches:
                price = int(m[0].replace(".", ""))

                if 25 <= price <= 20000:
                    prices.append(price)

        print(f"💰 FOUND PRICES: {prices}")
        return prices

    except Exception as e:
        print("❌ Search fejl:", e)
        return []


# -------------------------
# 🚀 API ENDPOINT
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("\n=== /analyze ===")

    contents = await file.read()
    print(f"📷 SIZE: {len(contents)}")

    img = compress_image(contents)

    # 1. AI DETECTION
    name = detect_object(img)

    if not name:
        return {
            "description": "Kunne ikke genkende objekt",
            "price": "0 kr",
            "price_range": "",
            "hits": 0
        }

    # 2. PRICE SEARCH
    prices = search_prices(name)

    if len(prices) < 3:
        print("⚠️ For få priser – fallback søgning")
        prices += search_prices(f"{name} til salg")

    if not prices:
        return {
            "description": name,
            "price": "Ingen data",
            "price_range": "",
            "hits": 0
        }

    prices.sort()

    # trim outliers
    cut = max(1, len(prices) // 5)
    trimmed = prices[cut:-cut] if len(prices) > 4 else prices

    final_price = int(median(trimmed))
    min_price = min(trimmed)
    max_price = max(trimmed)

    print(f"✅ RESULT: {name} → {final_price} kr")

    return {
        "description": name,
        "price": f"{final_price} kr",
        "price_range": f"{min_price}–{max_price} kr",
        "hits": len(prices)
    }


@app.get("/")
def root():
    return {"status": "ok", "version": "v6"}