import os
import base64
import requests
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from google import genai
from google.genai import types

app = FastAPI()

# CORS (frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🔥 AI PRICING AGENT v14 🔥")

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("🔑 SERPAPI:", "OK" if SERPAPI_KEY else "MISSING")
print("🔑 GEMINI:", "OK" if GEMINI_API_KEY else "MISSING")


# -------------------------
# ROOT
# -------------------------
@app.get("/")
def root():
    return {"status": "ok", "version": "v14"}


# -------------------------
# GEMINI OBJECT DETECTION
# -------------------------
def detect_object(image_bytes):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = """
Hvad er dette objekt? Svar kort på dansk.

Format:
navn, søgeord1, søgeord2

Eksempel:
trætønde, vintønde, træ tønde
"""

        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=[
                types.Content(
                    parts=[
                        types.Part(text=prompt),
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/jpeg",
                                data=image_bytes
                            )
                        )
                    ]
                )
            ]
        )

        text = (response.text or "").lower().strip()
        print("🧠 GEMINI RAW:", text)

        parts = [p.strip() for p in text.split(",") if p.strip()]

        if parts:
            return parts[0], parts[:3]

        return None, None

    except Exception as e:
        print("🚨 GEMINI FEJL:", str(e))
        return None, None


# -------------------------
# SERPAPI PRICE SEARCH
# -------------------------
def get_prices(query):
    try:
        print(f"🔍 SEARCH: {query}")

        url = "https://serpapi.com/search.json"
        params = {
            "q": f"{query} brugt til salg",
            "location": "Denmark",
            "hl": "da",
            "gl": "dk",
            "api_key": SERPAPI_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        prices = []

        # Google shopping results
        if "shopping_results" in data:
            for item in data["shopping_results"]:
                price_str = item.get("price", "")
                if price_str:
                    try:
                        price = int(
                            price_str.replace("kr.", "")
                            .replace("kr", "")
                            .replace(".", "")
                            .strip()
                        )
                        prices.append(price)
                    except:
                        pass

        print(f"💰 FOUND {len(prices)} prices")

        return prices

    except Exception as e:
        print("🚨 SERPAPI FEJL:", str(e))
        return []


# -------------------------
# ANALYZE ENDPOINT
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    contents = await file.read()
    print("📷 SIZE:", len(contents))

    # -------- COMPRESS IMAGE --------
    import io
    from PIL import Image

    image = Image.open(io.BytesIO(contents))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=60)

    compressed = buffer.getvalue()
    print("📦 COMPRESSED:", len(contents), "→", len(compressed))

    # -------- DETECT OBJECT --------
    name, keywords = detect_object(compressed)

    if not name:
        return {
            "name": "Kunne ikke analysere billede",
            "price": 0,
            "prices_found": 0
        }

    print("🧠 OBJECT:", name, keywords)

    # -------- SEARCH PRICES --------
    all_prices = []

    for kw in keywords:
        prices = get_prices(kw)
        all_prices.extend(prices)

    # fallback search
    if not all_prices:
        print("⚠️ fallback søgning")
        prices = get_prices(name)
        all_prices.extend(prices)

    # -------- RESULT --------
    if all_prices:
        avg_price = int(sum(all_prices) / len(all_prices))
        print(f"💰 RESULT: {name} → {avg_price} kr")

        return {
            "name": name,
            "price": avg_price,
            "prices_found": len(all_prices)
        }

    print("❌ INGEN PRISER FUNDET")

    return {
        "name": name,
        "price": 0,
        "prices_found": 0
    }