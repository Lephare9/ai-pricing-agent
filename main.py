from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64
import re

app = FastAPI()

# CORS (vigtigt for Netlify frontend)
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
                        {"text": "Beskriv objektet kort og præcist på dansk. Ingen forklaring, kun selve objektet og detaljer."},
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

        text = data["candidates"][0]["content"]["parts"][0]["text"]

        # ryd op
        text = text.strip().replace("\n", " ")
        text = text[0].upper() + text[1:]

        return text

    except Exception as e:
        print("AI fejl:", e)
        return "Ukendt objekt"


# -------------------------
# PRIS FRA SERP (SHOPPING)
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

        prices = []

        for item in data.get("shopping_results", []):
            price_str = item.get("price", "")

            if price_str:
                match = re.findall(r"\d+", price_str.replace(".", ""))
                if match:
                    prices.append(int(match[0]))

        if prices:
            prices.sort()
            median = prices[len(prices)//2]
            print("SHOPPING PRISER:", prices)
            return median

    except Exception as e:
        print("SHOPPING fejl:", e)

    # fallback til normal search (DBA osv.)
    try:
        url = "https://serpapi.com/search.json"

        params = {
            "q": f"{query} site:dba.dk",
            "hl": "da",
            "gl": "dk",
            "api_key": SERP_API_KEY
        }

        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        prices = []

        for item in data.get("organic_results", []):
            text = item.get("title", "") + " " + item.get("snippet", "")

            match = re.findall(r"\d{2,5}", text.replace(".", ""))
            for m in match:
                val = int(m)
                if 50 < val < 20000:
                    prices.append(val)

        if prices:
            prices.sort()
            median = prices[len(prices)//2]
            print("DBA PRISER:", prices)
            return median

    except Exception as e:
        print("DBA fejl:", e)

    return None


# -------------------------
# ROOT TEST
# -------------------------
@app.get("/")
def root():
    return {"status": "ok - v18 shopping aktiv"}


# -------------------------
# ANALYZE ENDPOINT
# -------------------------
@app.post("/analyze")
async def analyze(request: Request):
    try:
        body = await request.json()
        image_base64 = body.get("image", "").split(",")[-1]

        # AI beskrivelse
        description = describe_image(image_base64)

        # Pris
        price = get_price(description)

        if not price:
            return {
                "description": description,
                "price": "Ingen pris fundet",
                "note": "Ingen markedsdata"
            }

        return {
            "description": description,
            "price": f"{price} kr",
            "note": "Estimeret markedspris"
        }

    except Exception as e:
        print("FEJL:", e)
        return {
            "description": "Fejl",
            "price": "0 kr",
            "note": "Systemfejl"
        }