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


# 🧠 Gemini analyse (FORBEDRET)
def analyze_with_gemini(image_bytes):
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

        prompt = """
Beskriv dette møbel så præcist som muligt.

Svar KUN med:
- type (stol, sofa, bord osv.)
- materiale (træ, rattan, læder osv.)
- stil (retro, moderne, dansk design hvis relevant)

Eksempel:
"rattan lænestol retro"
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

        print("🧠 Gemini result:", result)

        # fallback hvis for generisk
        if len(result) < 5 or "møbel" in result:
            return "stol rattan"

        return result

    except Exception as e:
        print("Gemini error:", e)
        return "stol rattan"


# 🔍 SerpAPI søgning (FORBEDRET)
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
        for result in data.get("shopping_results", []):
            if "price" in result:
                digits = "".join(c for c in result["price"] if c.isdigit())
                if digits:
                    prices.append(int(digits))

        # fallback: organic snippets (ofte DBA lignende)
        for result in data.get("organic_results", []):
            snippet = result.get("snippet", "")
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

    # 🔥 3. Rens priser (fjern outliers)
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