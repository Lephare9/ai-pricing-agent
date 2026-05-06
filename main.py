from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

app = FastAPI()

# 🔥 CORS (KRITISK for Netlify → Railway)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # senere kan du begrænse til din Netlify URL
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

        # 🔹 Simpel beskrivelse (midlertidig)
        description = "Brugt møbel (automatisk analyse)"

        # 🔹 SerpApi (hvis key findes)
        serp_key = os.getenv("SERPAPI_KEY")

        if serp_key:
            print("🔍 Using SerpApi...")

            params = {
                "engine": "google",
                "q": "brugt møbel pris",
                "api_key": serp_key
            }

            res = requests.get("https://serpapi.com/search.json", params=params)
            data = res.json()

            prices = []

            try:
                results = data.get("organic_results", [])

                for r in results:
                    rich = r.get("rich_snippet", {})
                    detected = rich.get("detected_extensions", {})
                    price = detected.get("price")

                    if price:
                        prices.append(float(price))

                print("Prices found:", prices)

                if prices:
                    avg_price = int(sum(prices) / len(prices))
                else:
                    avg_price = 200  # fallback

            except Exception as e:
                print("Serp parsing error:", str(e))
                avg_price = 200

        else:
            print("⚠️ No SERPAPI_KEY → fallback mode")
            avg_price = 150

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