print("🔥 GEMINI V7 PRODUCTION MODE 🔥")

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

    try:
        res = requests.post(url, json=payload, timeout=40)
        data = res.json()

        if "candidates" not in data:
            return None, "timeout"

        text = data["candidates"][0]["content"]["parts"][0].get("text", "")

        if not text or "{" not in text:
            return None, "ai_failed"

        return text, None

    except Exception as e:
        print("GEMINI ERROR:", e)
        return None, "timeout"


def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        return json.loads(match.group()), None
    except:
        print("JSON ERROR:", text)
        return {}, "parse_error"


def identify_object(image_base64):

    prompt = """
Analyser billedet.

Returnér KUN JSON:

{
  "name": "",
  "condition": "",
  "confidence": 0.0
}

KRAV:
- max 5 linjer
- kort og konkret
- inkluder model hvis muligt
- fx: "IKEA MALM kommode, hvid, brugt stand"
"""

    text, err = call_gemini(prompt, image_base64)
    if err:
        return None, err

    parsed, parse_err = extract_json(text)
    if parse_err:
        return None, parse_err

    if not parsed.get("name"):
        return None, "ai_failed"

    return parsed, None


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
- snævert interval
"""

    text, err = call_gemini(prompt, image_base64)
    if err:
        return None, err

    parsed, parse_err = extract_json(text)
    if parse_err:
        return None, parse_err

    if parsed.get("price_max", 0) <= 0:
        return None, "ai_failed"

    return parsed, None


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    identity, err = identify_object(base64_image)
    if err:
        return {
            "description": "Ukendt",
            "price_range": "-",
            "confidence": 0,
            "error": err
        }

    price, err = price_object(base64_image, json.dumps(identity))
    if err:
        return {
            "description": identity.get("name", "Ukendt"),
            "price_range": "-",
            "confidence": 0,
            "error": err
        }

    price_min = int(price.get("price_min", 0))
    price_max = int(price.get("price_max", 0))

    if price_max > 0:
        diff = price_max - price_min
        if diff > price_max * 0.3:
            mid = (price_min + price_max) // 2
            price_min = int(mid * 0.85)
            price_max = int(mid * 1.15)

    return {
        "description": identity.get("name", "Ukendt"),
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": int(price.get("confidence", 0) * 100),
        "error": None
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "production"}