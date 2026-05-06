import os
import base64
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import requests

print("🔥 AI PRICING AGENT v17 🔥")

# =========================
# KEYS
# =========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not GEMINI_API_KEY:
    print("❌ GEMINI KEY MANGLER")
else:
    print("🔑 GEMINI: OK")

if not SERPAPI_KEY:
    print("❌ SERPAPI KEY MANGLER")
else:
    print("🔑 SERPAPI: OK")

genai.configure(api_key=GEMINI_API_KEY)

# =========================
# APP
# =========================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # senere: din netlify url
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"status": "ok", "version": "v17"}

# =========================
# ANALYZE
# =========================
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    try:
        image_bytes = await file.read()
        print(f"📷 SIZE: {len(image_bytes)}")

        # =========================
        # GEMINI ANALYSE
        # =========================
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")

            response = model.generate_content([
                "Hvad er dette objekt? Svar kort (max 3 ord)",
                image_bytes
            ])

            text = response.text.strip().lower()
            print("🧠 GEMINI:", text)

            # fallback hvis model siger noget mærkeligt
            if not text or len(text) > 50:
                text = "genstand"

        except Exception as e:
            print("🚨 GEMINI FEJL:", str(e))
            return {
                "title": "Kunne ikke analysere billede",
                "price": 0,
                "results": []
            }

        # =========================
        # SERPAPI SEARCH
        # =========================
        try:
            print("🔍 SEARCH:", text)

            params = {
                "engine": "google",
                "q": f"{text} brugt pris",
                "api_key": SERPAPI_KEY
            }

            r = requests.get("https://serpapi.com/search", params=params)
            data = r.json()

            prices = []

            if "shopping_results" in data:
                for item in data["shopping_results"]:
                    if "price" in item:
                        p = item["price"]
                        # træk tal ud
                        p = "".join(c for c in p if c.isdigit())
                        if p:
                            prices.append(int(p))

            print("💰 FOUND:", prices)

            if prices:
                avg_price = int(sum(prices) / len(prices))
            else:
                avg_price = 100

        except Exception as e:
            print("🚨 SERPAPI FEJL:", str(e))
            avg_price = 100
            prices = []

        # =========================
        # RETURN
        # =========================
        return {
            "title": text,
            "price": avg_price,
            "results": prices
        }

    except Exception as e:
        print("🔥 CRASH:", str(e))
        return {
            "title": "Fejl",
            "price": 0,
            "results": []
        }