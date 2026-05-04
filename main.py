print("🔥 GEMINI V7 FAST MODE 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ---------- CALL GEMINI ----------
def call_gemini(prompt, image_base64, model):

    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={GEMINI_API_KEY}"

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

    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()

        if "candidates" not in data:
            return None

        text = data["candidates"][0]["content"]["parts"][0].get("text", "")

        if not text or "{" not in text:
            return None

        return text

    except Exception as e:
        print("GEMINI ERROR:", e)
        return None


# ---------- PARSE ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        return json.loads(match.group())
    except:
        return {}


# ---------- STEP 1 ----------
def identify_object(image_base64):

    prompt = """
Analyser billedet.

Returnér KUN JSON:

{
  "name": "",
  "confidence": 0.0
}

KRAV:
- vær specifik
"""

    # 🔥 FLASH først (hurtigere)
    for model in ["gemini-2.5-flash", "gemini-2.5-pro"]:
        result = call_gemini(prompt, image_base64, model)
        if result:
            parsed = extract_json(result)
            if parsed.get("name"):
                return parsed

    return None


# ---------- STEP 2 ----------
def price_object(image_base64, identity_json):

    prompt = f"""
Vurder brugtpris i Danmark.

Produkt:
{identity_json}

Returnér KUN JSON:

{{
  "price_min": 0,
  "price_max": 0,
  "confidence": 0.0
}}

Regler:
- max 30% forskel mellem min og max
- vælg snævert interval
- undgå brede ranges
"""

    # 🔥 FLASH først igen
    for model in ["gemini-2.5-flash", "gemini-2.5-pro"]:
        result = call_gemini(prompt, image_base64, model)
        if result:
            parsed = extract_json(result)
            if parsed.get("price_max", 0) > 0:
                return parsed

    return None


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    identity = identify_object(base64_image)

    if not identity:
        return {
            "description": "Ukendt",
            "price_range": "-",
            "confidence": 0
        }

    price = price_object(base64_image, json.dumps(identity))

    if not price:
        return {
            "description": identity.get("name", "Ukendt"),
            "price_range": "-",
            "confidence": 0
        }

    price_min = int(price.get("price_min", 0))
    price_max = int(price.get("price_max", 0))

    # 🔥 HARD CLAMP (beholder din kvalitet)
    if price_max > 0:
        diff = price_max - price_min
        if diff > price_max * 0.3:
            mid = (price_min + price_max) // 2
            price_min = int(mid * 0.85)
            price_max = int(mid * 1.15)

    return {
        "description": identity.get("name", "Ukendt"),
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": int(price.get("confidence", 0) * 100)
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "fast"}