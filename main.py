print("🔥 AI PRICING AGENT V6.2 🔥")

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
# Komprimer billede
# -------------------------
def compress_image(image_bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((800, 800))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except:
        return image_bytes


# -------------------------
# Gemini (simpel)
# -------------------------
def detect_object(image_bytes):
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-1.5-flash")

        response = model.generate_content([
            {"mime_type": "image/jpeg", "data": image_bytes},
            "Hvad er dette? svar 1-2 ord"
        ])

        text = response.text.strip().lower()
        print("GEMINI:", text)

        if not text or len(text) < 2:
            return "trækasse"   # fallback for test

        return text

    except Exception as e:
        print("Gemini fejl:", e)
        return "trækasse"   # fallback for test


# -------------------------
# Pris extraction
# -------------------------
def extract_prices(text):
    matches = re.findall(r'(\d[\d.]*)\s*(kr|,-)', text.lower())
    prices = []

    for m in matches:
        val = int(m[0].replace(".", ""))
        if 20 < val < 20000:
            prices.append(val)

    return prices


# -------------------------
# Search
# -------------------------
def search_prices(query):
    print("SEARCH:", query)

    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": SERPAPI_KEY,
            "gl": "dk",
            "hl": "da"
        }

        r = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data = r.json()

        prices = []

        for res in data.get("organic_results", []):
            text = res.get("title", "") + " " + res.get("snippet", "")
            found = extract_prices(text)
            prices += found

        print("PRICES FOUND:", prices)
        return prices

    except Exception as e:
        print("Search fejl:", e)
        return []


# -------------------------
# Endpoint
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    contents = await file.read()
    img = compress_image(contents)

    # 1. hvad er det
    name = detect_object(img)

    # 2. queries (meget simple!)
    queries = [
        f"site:dba.dk {name}",
        f"{name} til salg"
    ]

    all_prices = []

    for q in queries:
        p = search_prices(q)
        all_prices += p

    # 3. resultat
    if all_prices:
        all_prices.sort()
        final = int(median(all_prices))
        min_p = min(all_prices)
        max_p = max(all_prices)
    else:
        final = 0
        min_p = 0
        max_p = 0

    return {
        "description": name,
        "price": f"{final} kr",
        "price_range": f"{min_p}–{max_p} kr",
        "hits": len(all_prices)
    }


@app.get("/")
def root():
    return {"status": "ok"}