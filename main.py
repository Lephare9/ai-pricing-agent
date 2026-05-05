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


# ---------- GEMINI ----------
def call_gemini(prompt, image_base64=None):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    parts = [{"text": prompt}]

    if image_base64:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_base64
            }
        })

    payload = {"contents": [{"parts": parts}]}

    for _ in range(2):
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


# ---------- PARSE ----------
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
Identificér produktet præcist.

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
- kitchen
- hobby
- other

Regler:
- vær konkret
- find model hvis muligt
"""

    return call_gemini(prompt, image_base64)


# ---------- STEP 2: SMART PRICE (TEKST ONLY) ----------
def estimate_price_ai(name, brand):

    prompt = f"""
Find realistisk brugtpris i Danmark.

Produkt: {name}
Brand: {brand}

Tænk som DBA / Facebook Marketplace.

Returnér KUN JSON:

{{
  "price_min": 0,
  "price_max": 0,
  "confidence": 0.0
}}

REGLER:
- brug typiske brugtpriser i DK
- hvis billigt objekt → lav pris (20–300 kr)
- hvis design → højere
- snævert interval (max 30%)
- hvis ukendt → realistisk gennemsnit
"""

    return call_gemini(prompt)


# ---------- FALLBACK ----------
def fallback_price(category, name):

    category = category.lower()
    name = name.lower()

    if any(x in name for x in ["mus", "mouse"]):
        return 50, 200

    if any(x in name for x in ["raflebæger", "terning", "dice"]):
        return 100, 300

    base = {
        "computer accessory": (50, 300),
        "furniture": (300, 2000),
        "lamp": (100, 1500),
        "decor": (50, 600),
        "kitchen": (50, 500),
        "hobby": (50, 300),
        "other": (80, 500)
    }

    return base.get(category, (80, 500))


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

    # STEP 2 (AI PRICE)
    price_raw = estimate_price_ai(name, brand)
    price = extract_json(price_raw) if price_raw else {}

    price_min = int(price.get("price_min") or 0)
    price_max = int(price.get("price_max") or 0)
    confidence = int((price.get("confidence") or 0) * 100)

    # FALLBACK hvis AI fejler
    if price_min == 0 or price_max == 0:
        price_min, price_max = fallback_price(category, name)
        confidence = 60

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": confidence
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v4-hybrid"}