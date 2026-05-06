print("🔥 AI PRICING AGENT v4 🔥")

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# -------------------------
# 🖼️ Komprimer billede
# -------------------------
def compress_image(image_bytes, max_size=800):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_size, max_size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except:
        return image_bytes


# -------------------------
# 🔍 Gemini (simpel + stabil)
# -------------------------
def detect_object(image_bytes):
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-1.5-flash")

        response = model.generate_content([
            {"mime_type": "image/jpeg", "data": image_bytes},
            "Hvad er dette? Svar med 2-3 ord på dansk. fx: 'rattan stol', 'trækasse', 'lænestol'"
        ])

        text = response.text.strip().lower()

        if not text or len(text) < 3:
            return "møbel", ["møbel"]

        return text, [text]

    except Exception as e:
        print("Gemini fejl:", e)
        return "møbel", ["møbel"]


# -------------------------
# 🔎 Google Lens (SerpAPI)
# -------------------------
def reverse_image_search(image_bytes):
    try:
        image_base64 = base64.b64encode(image_bytes).decode()

        params = {
            "engine": "google_lens",
            "api_key": SERPAPI_KEY,
            "image_content": image_base64
        }

        res = requests.get("https://serpapi.com/search", params=params, timeout=15)
        data = res.json()

        titles = []

        if "visual_matches" in data:
            for item in data["visual_matches"][:5]:
                if "title" in item:
                    titles.append(item["title"].lower())

        return " ".join(titles)

    except Exception as e:
        print("Lens fejl:", e)
        return ""


# -------------------------
# 💰 DBA søgning (bedre)
# -------------------------
def search_prices(query):
    try:
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
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()

            matches = re.findall(r'(\d[\d.]*)\s*(kr|,-)', text)

            for m in matches:
                price = int(m[0].replace(".", ""))

                if 25 <= price <= 15000:
                    prices.append(price)

        return prices[:10]

    except Exception as e:
        print("Search fejl:", e)
        return []


# -------------------------
# 🚀 ENDPOINT
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    contents = await file.read()
    compressed = compress_image(contents)

    # 1. hvad er det
    name, keywords = detect_object(compressed)

    # 2. lens hjælper
    lens_text = reverse_image_search(compressed)

    # 3. søgning
    query = f"{name} {lens_text} til salg"
    prices = search_prices(query)

    # fallback
    if not prices:
        prices = search_prices(f"{name} møbel til salg")

    # beregn pris
    if prices:
        prices.sort()
        cut = max(1, len(prices)//5)
        trimmed = prices[cut:-cut] if len(prices) > 4 else prices

        final_price = int(median(trimmed))
        min_price = min(trimmed)
        max_price = max(trimmed)
    else:
        final_price = 100
        min_price = 50
        max_price = 200

    return {
        "description": name,
        "price": f"{final_price} kr",
        "price_range": f"{min_price}–{max_price} kr",
        "hits": len(prices)
    }


@app.get("/")
def root():
    return {"status": "ok"}