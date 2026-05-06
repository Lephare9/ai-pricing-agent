import os
import io
import requests
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from google import genai
from google.genai import types
from PIL import Image

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🔥 AI PRICING AGENT v16 🔥")

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("🔑 SERPAPI:", "OK" if SERPAPI_KEY else "MISSING")
print("🔑 GEMINI:", "OK" if GEMINI_API_KEY else "MISSING")


@app.get("/")
def root():
    return {"status": "ok", "version": "v16"}


# ---------------- GEMINI ----------------
def detect_object(image_bytes):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = "Hvad er dette objekt? Svar kort på dansk, fx: stol, sofa, bord"

        response = client.models.generate_content(
            model="gemini-1.5-flash-latest",
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

        if not text:
            return None, None

        words = [w.strip() for w in text.split(",") if w.strip()]

        return words[0], words

    except Exception as e:
        print("🚨 GEMINI FEJL:", str(e))
        return None, None


# ---------------- SERP ----------------
def get_prices(query):
    try:
        print("🔍 SEARCH:", query)

        url = "https://serpapi.com/search.json"
        params = {
            "q": f"{query} brugt",
            "hl": "da",
            "gl": "dk",
            "api_key": SERPAPI_KEY
        }

        data = requests.get(url, params=params).json()

        prices = []

        if "shopping_results" in data:
            for item in data["shopping_results"]:
                price = item.get("price")
                if price:
                    try:
                        p = int(
                            price.replace("kr.", "")
                            .replace("kr", "")
                            .replace(".", "")
                            .strip()
                        )
                        prices.append(p)
                    except:
                        pass

        print("💰 FOUND:", len(prices))
        return prices

    except Exception as e:
        print("🚨 SERP FEJL:", str(e))
        return []


# ---------------- ANALYZE ----------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    try:
        contents = await file.read()
        print("📷 SIZE:", len(contents))

        # --- image load ---
        try:
            image = Image.open(io.BytesIO(contents))
        except Exception as e:
            return {
                "name": "Billede fejl",
                "price": 0,
                "prices_found": 0,
                "error": str(e)
            }

        # --- compress ---
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=60)
        img = buffer.getvalue()

        print("📦 COMPRESSED:", len(img))

        # --- detect ---
        name, keywords = detect_object(img)

        if not name:
            return {
                "name": "Gemini fejlede",
                "price": 0,
                "prices_found": 0
            }

        print("🧠 OBJECT:", name, keywords)

        # --- search ---
        all_prices = []

        for kw in keywords:
            all_prices += get_prices(kw)

        if not all_prices:
            print("⚠️ fallback søgning")
            all_prices += get_prices(name)

        if all_prices:
            avg = int(sum(all_prices) / len(all_prices))
            print("💰 RESULT:", name, avg)

            return {
                "name": name,
                "price": avg,
                "prices_found": len(all_prices)
            }

        return {
            "name": name,
            "price": 0,
            "prices_found": 0
        }

    except Exception as e:
        print("🔥 CRASH:", str(e))
        return {
            "name": "Server fejl",
            "price": 0,
            "prices_found": 0,
            "error": str(e)
        }