from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")


# -------------------------
# AI BESKRIVELSE
# -------------------------
def describe_image(base64_image):
    try:
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": "Beskriv objektet kort på dansk, fx: 'Barstol i træ med lædersæde'"},
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

        res = requests.post(url, json=payload, timeout=20)
        data = res.json()

        print("RAW GEMINI:", data)

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().replace("\n", " ")
        return text[0].upper() + text[1:]

    except Exception as e:
        print("AI fejl:", e)
        return "Ukendt objekt"


# -------------------------
# SERP PRIS
# -------------------------
def get_price(query):
    try:
        url = "https://serpapi.com/search.json"

        params = {
            "engine": "google_shopping",
            "q": query,
            "hl": "da",
            "gl": "dk",
            "api_key": SERP_API_KEY
        }

        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        print("SERP RAW:", data)

        prices = []

        for item in data.get("shopping_results", []):
            price_str = item.get("price", "")
            match = re.findall(r"\d+", price_str.replace(".", ""))
            if match:
                prices.append(int(match[0]))

        if prices:
            prices.sort()
            return prices[len(prices)//2]

    except Exception as e:
        print("SERP fejl:", e)

    return None


# -------------------------
# ROOT
# -------------------------
@app.get("/")
def root():
    return {"status": "ok - v18.1 stable"}


# -------------------------
# ANALYZE
# -------------------------
@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        print("REQUEST BODY:", body)

        image_data = body.get("image")

        if not image_data:
            return {"description": "Ingen billede", "price": "0 kr"}

        # håndter både raw og data URL
        if "," in image_data:
            image_base64 = image_data.split(",")[1]
        else:
            image_base64 = image_data

        description = describe_image(image_base64)
        price = get_price(description)

        if not price:
            return {
                "description": description,
                "price": "Ingen pris fundet"
            }

        return {
            "description": description,
            "price": f"{price} kr"
        }

    except Exception as e:
        print("TOTAL FEJL:", e)
        return {
            "description": "Systemfejl",
            "price": "0 kr"
        }
        return {
            "description": "Fejl",
            "price": "0 kr",
            "note": "Systemfejl"
        }