print("🔥 AI PRICING AGENT v12 🔥")

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

print("🔑 SERPAPI:", "OK" if SERPAPI_KEY else "MISSING")
print("🔑 GEMINI:", "OK" if GEMINI_API_KEY else "MISSING")


# -------------------------
# 🖼️ KOMPRESS
# -------------------------
def compress_image(image_bytes, max_size=800):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_size, max_size))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)

        compressed = buf.getvalue()
        print(f"📦 COMPRESSED: {len(image_bytes)} → {len(compressed)}")

        return compressed

    except Exception as e:
        print("Compress fejl:", e)
        return image_bytes


# -------------------------
# 🧠 GEMINI
# -------------------------
def detect_object(image_bytes):
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)

        # ✅ MODEL DER VIRKER
        model = genai.GenerativeModel("gemini-1.5-pro-latest")

        prompt = """
Hvad er dette objekt?

Svar KUN sådan:
navn, søgeord1, søgeord2

Eksempel:
trætønde, vintønde, træ tønde
"""

        # ✅ VIGTIGT: prompt først!
        response = model.generate_content([
            prompt,
            {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
        ])

        text = (response.text or "").lower().strip()

        print("🧠 GEMINI RAW:", text)

        parts = [p.strip() for p in text.split(",") if p.strip()]

        if parts:
            name = parts[0]
            keywords = parts[:3]
            return name, keywords

        return None, None

    except Exception as e:
        print("🚨 GEMINI FEJL:", str(e))
        return None, None


# -------------------------
# 💰 SEARCH
# -------------------------
def search_prices(query):
    try:
        url = "https://serpapi.com/search.json"

        params = {
            "engine": "google",
            "q": f"site:dba.dk {query}",
            "api_key": SERPAPI_KEY,
            "gl": "dk",
            "hl": "da",
            "num": 10
        }

        print("🔍 SEARCH:", query)

        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        prices = []

        for r in data.get("organic_results", []):
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()

            matches = re.findall(r'(\d[\d.]{1,6})\s*(?:kr|,-|dkk)', text)

            for m in matches:
                price = int(m.replace(".", ""))
                if 25 <= price <= 15000:
                    prices.append(price)

        print(f"💰 FOUND {len(prices)} prices")

        return prices

    except Exception as e:
        print("Pris fejl:", e)
        return []


# -------------------------
# 🚀 ANALYZE
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("\n=== /analyze ===")

    contents = await file.read()
    print(f"📷 SIZE: {len(contents)}")

    compressed = compress_image(contents)

    # 🧠 Gemini
    name, keywords = detect_object(compressed)

    # ❗ STOP hvis Gemini fejler
    if not name:
        return {
            "description": "Gemini fejlede",
            "price": "0 kr",
            "price_range": "",
            "hits": 0
        }

    print("🧠 OBJECT:", name, keywords)

    # 💰 søg priser
    all_prices = []

    for kw in keywords:
        prices = search_prices(kw)
        all_prices.extend(prices)

    if not all_prices:
        print("⚠️ ingen priser fundet")
        return {
            "description": name,
            "price": "Ingen data",
            "price_range": "",
            "hits": 0
        }

    # 📊 beregn
    all_prices.sort()

    cut = max(1, len(all_prices) // 5)
    trimmed = all_prices[cut:-cut] if len(all_prices) > 4 else all_prices

    final_price = int(median(trimmed))
    min_price = min(trimmed)
    max_price = max(trimmed)

    print(f"💰 RESULT: {name} → {final_price} kr")

    return {
        "description": name,
        "price": f"{final_price} kr",
        "price_range": f"{min_price}–{max_price} kr",
        "hits": len(all_prices)
    }


# -------------------------
# ROOT
# -------------------------
@app.get("/")
def root():
    return {"status": "ok", "version": "v12"}