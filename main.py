from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64

app = FastAPI()

# 🔓 CORS (Netlify fix)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("🚀 Backend starting...")


# 🧠 Gemini analyse (FIXED)
def analyze_with_gemini(image_bytes):
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

        prompt = """
Beskriv objektet på billedet så præcist som muligt.

Svar KUN med:
- type (stol, bord, kasse, lampe osv.)
- materiale (træ, metal, rattan osv.)
- evt stil (retro, vintage, dansk design)

Eksempel:
"trækasse vintage"
"rattan stol retro"
"""

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64_image
                            }
                        }
                    ]
                }
            ]
        }

        res = requests.post(url, json=payload)
        data = res.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        result = text.strip().lower()

        print("🧠 Gemini raw:", result)

        # 🔥 smarter fallback (overskriver IKKE gode svar)
        bad_words = ["møbel", "ting", "objekt", "genstand"]

        if len(result) < 3 or result in bad_words:
            print("⚠️ Weak Gemini result → fallback")
            return "brugt møbel"

        return result

    except Exception as e:
        print("Gemini error:", e)
        return "brugt møbel"


# 🔍 SerpAPI søgning
def search_prices(query):
    try:
        print(f"🔍 Searching for: {query}")

        url = "https://serpapi.com/search.json"

        params = {
            "q": f"{query} brugt til salg danmark",
            "engine": "google",
            "api_key": SERPAPI_KEY
        }

        res = requests.get(url, params=params)
        data = res.json()

        prices = []

        # shopping results
        for r in data.get("shopping_results", []):
            if "price" in r:
                digits = "".join(c for c in r["price"] if c.isdigit())
                if digits:
                    prices.append(int(digits))

        # organic fallback (fx DBA snippets)
        for r in data.get("organic_results", []):
            snippet = r.get("snippet", "")
            digits = "".join(c for c in snippet if c.isdigit())

            if digits:
                val = int(digits)
                if 50 < val < 20000:
                    prices.append(val)

        print("💰 Raw prices:", prices)

        return prices

    except Exception as e:
        print("SerpAPI error:", e)
        return []


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze called ===")

    image_bytes = await file.read()
    print(f"File size: {len(image_bytes)} bytes")

    # 🧠 1. Gemini
    description = analyze_with_gemini(image_bytes)

    # 🔍 2. SerpAPI
    prices = search_prices(description)

    # 🔥 3. Rens priser
    clean_prices = [p for p in prices if 50 < p < 10000]
    print("✅ Filtered prices:", clean_prices)

    # 📊 4. Median
    if clean_prices:
        clean_prices.sort()
        mid = len(clean_prices) // 2

        if len(clean_prices) % 2 == 0:
            price = int((clean_prices[mid - 1] + clean_prices[mid]) / 2)
        else:
            price = clean_prices[mid]
    else:
        price = 300  # fallback

    print("📊 Final price:", price)

    return {
        "description": description,
        "price": f"{price} kr"
    }


@app.get("/")
def root():
    return {"status": "ok"}