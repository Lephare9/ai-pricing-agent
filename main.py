from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64

app = FastAPI()

# 🔓 CORS (vigtigt for Netlify)
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


# 🧠 Gemini analyse
def analyze_with_gemini(image_bytes):
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": "Hvad er dette møbel? Svar kort og præcist."},
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
        print("🧠 Gemini:", text)

        return text.strip()

    except Exception as e:
        print("Gemini error:", e)
        return "brugt møbel"


# 🔍 SerpAPI søgning
def search_prices(query):
    try:
        print(f"🔍 Searching for: {query}")

        url = "https://serpapi.com/search.json"

        params = {
            "q": f"{query} brugt danmark pris",
            "engine": "google",
            "api_key": SERPAPI_KEY
        }

        res = requests.get(url, params=params)
        data = res.json()

        prices = []

        # prøv forskellige felter
        for result in data.get("shopping_results", []):
            if "price" in result:
                price_str = result["price"]
                digits = "".join(c for c in price_str if c.isdigit())
                if digits:
                    prices.append(int(digits))

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

    # 🔥 3. Rens data (fjerner outliers)
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