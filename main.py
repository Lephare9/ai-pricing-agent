print("🔥 AI PRICING AGENT v9 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64
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


# -------------------------
# 🖼️ KOMPRESSER BILLEDE
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
# 🔎 GOOGLE LENS (FIXET)
# -------------------------
def search_lens(image_bytes):
    try:
        url = "https://serpapi.com/search.json"

        b64 = base64.b64encode(image_bytes).decode()

        params = {
            "engine": "google_lens",
            "api_key": SERPAPI_KEY,
            "hl": "da",
            "gl": "dk",
            "image_content": b64   # ✅ FIX
        }

        res = requests.get(url, params=params, timeout=20)
        data = res.json()

        keywords = []

        for r in data.get("visual_matches", [])[:5]:
            title = r.get("title", "")
            if title:
                keywords.append(title.lower())

        # 🔥 rens keywords
        cleaned = []
        for k in keywords:
            k = re.sub(r"[^a-zA-Z0-9æøåÆØÅ ]", "", k)
            k = k.replace("vintage", "").replace("wood", "")
            k = k.strip()
            if len(k) > 3:
                cleaned.append(k)

        print("🔎 LENS:", cleaned)

        return cleaned

    except Exception as e:
        print("Lens fejl:", e)
        return []


# -------------------------
# 💰 PRISSØGNING
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

            matches = re.findall(
                r'(\d[\d.]{1,6})\s*(?:kr|,-|dkk)',
                text
            )

            for m in matches:
                price = int(m.replace(".", ""))

                if 25 <= price <= 15000:
                    prices.append(price)

        return prices

    except Exception as e:
        print("Pris søg fejl:", e)
        return []


# -------------------------
# 🚀 ANALYZE
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    contents = await file.read()
    print(f"📷 SIZE: {len(contents)}")

    compressed = compress_image(contents)

    # 🔎 Lens
    keywords = search_lens(compressed)

    # fallback hvis Lens fejler
    if not keywords:
        keywords = ["møbel", "til salg"]

    print("🔎 FINAL SEARCH TERMS:", keywords)

    # 💰 hent priser
    all_prices = []

    for kw in keywords[:3]:
        prices = search_prices(kw)
        all_prices.extend(prices)

    # fallback igen hvis ingen data
    if not all_prices:
        print("⚠️ fallback søgning")
        all_prices.extend(search_prices("møbel dba"))

    # -------------------------
    # 📊 BEREGN PRIS
    # -------------------------
    if all_prices:
        all_prices.sort()

        cut = max(1, len(all_prices) // 5)
        trimmed = all_prices[cut:-cut] if len(all_prices) > 4 else all_prices

        final_price = int(median(trimmed))
        min_price = min(trimmed)
        max_price = max(trimmed)

        label = keywords[0]

    else:
        final_price = 100
        min_price = 50
        max_price = 200
        label = "genstand"

    print(f"💰 RESULT: {label} → {final_price} kr")

    return {
        "description": label,
        "price": f"{final_price} kr",
        "price_range": f"{min_price}–{max_price} kr",
        "hits": len(all_prices)
    }


# -------------------------
# ROOT
# -------------------------
@app.get("/")
def root():
    return {"status": "ok", "version": "v9"}