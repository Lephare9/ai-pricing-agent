from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64

app = FastAPI()

# 🔓 CORS
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


# 🧠 1. Gemini analyse (MEGET præcis)
def analyze_with_gemini(image_bytes):
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

        prompt = """
Analyser billedet meget præcist.

1. Hvad er objektet (fx stol, kasse, bord)?
2. Hvilket materiale?
3. Er der tekst på objektet? Skriv teksten.

Svar KUN som én linje.

Eksempel:
"trækasse træ D.D.S.F Aalborg"
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

        print("🧠 Gemini:", result)

        if not result:
            return "trækasse"

        return result

    except Exception as e:
        print("Gemini error:", e)
        return "trækasse"


# 🔍 2. SerpAPI søgning (EXACT MATCH fokus)
def search_prices(query):
    try:
        print(f"🔍 Searching for: {query}")

        url = "https://serpapi.com/search.json"

        params = {
            "q": f"{query} brugt til salg",
            "engine": "google",
            "api_key": SERPAPI_KEY,
            "num": 20
        }

        res = requests.get(url, params=params)
        data = res.json()

        prices = []

        # 🛒 shopping results
        for r in data.get("shopping_results", []):
            if "price" in r:
                digits = "".join(c for c in r["price"] if c.isdigit())
                if digits:
                    prices.append(int(digits))

        # 🌐 organic results (DBA / marketplace)
        for r in data.get("organic_results", []):
            snippet = (r.get("snippet") or "").lower()
            title = (r.get("title") or "").lower()

            # 🔥 match query ord (bedre relevans)
            if any(word in snippet or word in title for word in query.split()):
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

    # 🔍 2. Serp
    prices = search_prices(description)

    # 🔥 3. Rens data
    clean_prices = [p for p in prices if 50 < p < 10000]
    print("✅ Filtered:", clean_prices)

    # 📊 4. Median
    if clean_prices:
        clean_prices.sort()
        mid = len(clean_prices) // 2

        if len(clean_prices) % 2 == 0:
            price = int((clean_prices[mid - 1] + clean_prices[mid]) / 2)
        else:
            price = clean_prices[mid]
    else:
        price = 200  # fallback

    print("📊 Final price:", price)

    return {
        "description": description,
        "price": f"{price} kr"
    }


@app.get("/")
def root():
    return {"status": "ok"}