from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re, time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ---------- GEMINI CALL ----------
def call_gemini(prompt, image_base64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                }
            ]
        }]
    }

    for _ in range(2):  # retry
        try:
            res = requests.post(url, json=payload, timeout=20)
            data = res.json()

            if "candidates" not in data:
                print("NO CANDIDATES:", data)
                time.sleep(1)
                continue

            return data["candidates"][0]["content"]["parts"][0]["text"]

        except Exception as e:
            print("ERROR:", e)
            time.sleep(1)

    return None


# ---------- JSON PARSER ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        print("JSON ERROR:", text)
        return {}


# ---------- STEP 1: IDENTIFY ----------
def identify_object(image_base64):

    prompt = """
Identificér objekt præcist.

Returnér KUN JSON:

{
  "name": "",
  "brand": "",
  "category": ""
}

Kategorier:
- computer accessory
- furniture
- lamp
- decor
- other

Regler:
- vær konkret
- find brand hvis muligt
"""

    return call_gemini(prompt, image_base64)


# ---------- PRICE ENGINE ----------
def estimate_price(category, brand):

    base = {
        "computer accessory": (50, 300),
        "furniture": (300, 2000),
        "lamp": (100, 1500),
        "decor": (50, 800),
        "other": (100, 1000)
    }

    price_min, price_max = base.get(category, (100, 1000))

    brand = brand.lower()

    premium = ["bolia", "hay", "mater", "muuto", "fritz hansen"]
    cheap = ["ikea"]

    if brand in premium:
        price_min *= 2
        price_max *= 2.5

    elif brand in cheap:
        price_min *= 0.6
        price_max *= 0.7

    return int(price_min), int(price_max)


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1
    identity_raw = identify_object(base64_image)
    identity = extract_json(identity_raw) if identity_raw else {}

    name = identity.get("name") or "Ukendt produkt"
    brand = identity.get("brand") or "ukendt"
    category = identity.get("category") or "other"

    # STEP 2 (AI price – hvis muligt)
    price_min = 0
    price_max = 0

    # fallback til kategori-baseret
    if price_min == 0:
        price_min, price_max = estimate_price(category, brand)

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": 70  # stabil default
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v2-stable"}