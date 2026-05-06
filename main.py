from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import re

app = FastAPI()

# 🔥 CORS (vigtigt for Netlify frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # kan senere begrænses
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🚀 Backend starting...")


# ✅ Health check
@app.get("/")
def root():
    return {"status": "ok"}


# ✅ Analyze endpoint
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze called ===")

    try:
        contents = await file.read()
        print(f"File size: {len(contents)} bytes")

        # 🔹 Midlertidig beskrivelse (vi opgraderer senere med Gemini)
        description = "Brugt møbel"

        # 🔹 Hent SerpApi key
        serp_key = os.getenv("SERPAPI_KEY")
        print("SERP KEY FOUND:", bool(serp_key))

        prices = []

        if serp_key:
            print("🔍 Using SerpApi...")

            params = {
                "engine": "google",
                "q": "brugt sofa pris",
                "api_key": serp_key,
                "google_domain": "google.dk",
                "gl": "dk",
                "hl": "da"
            }

            res = requests.get("https://serpapi.com/search.json", params=params)
            data = res.json()

            # 🔥 1. Shopping results (BEDST)
            shopping = data.get("shopping_results", [])

            for item in shopping:
                price = item.get("price")

                if price:
                    cleaned = (
                        price.replace(".", "")
                        .replace(",", "")
                        .replace("kr", "")
                        .replace("DKK", "")
                        .strip()
                    )

                    try:
                        prices.append(int(cleaned))
                    except:
                        pass

            # 🔥 2. Fallback: organic results
            if not prices:
                for r in data.get("organic_results", []):
                    snippet = r.get("snippet", "")

                    matches = re.findall(r'(\d+[.,]?\d*)\s?kr', snippet.lower())

                    for m in matches:
                        cleaned = m.replace(".", "").replace(",", "")
                        try:
                            prices.append(int(cleaned))
                        except:
                            pass

            print("Prices found:", prices)

        else:
            print("⚠️ No SERPAPI_KEY → fallback mode")

        # 🔹 Beregn pris
        if prices:
            avg_price = int(sum(prices) / len(prices))
        else:
            avg_price = 200  # fallback

        return {
            "description": description,
            "price": f"{avg_price} kr"
        }

    except Exception as e:
        print("❌ ERROR:", str(e))
        return {
            "description": "Systemfejl",
            "price": "0 kr"
        }