print("🔥 GEMINI V7 2-STEP AGENT 🔥")

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
        res = requests.post(url, json=payload, timeout=20)
        data = res.json()

        print(f"🔥 MODEL {model}:", data)

        if "candidates" not in data:
            return None

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        print("🔥 GEMINI ERROR:", e)
        return None


# ---------- STEP 1: IDENTITY ----------
def identify_object(image_base64):

    prompt = """
Du analyserer et billede.

MÅ IKKE være generisk.

Returnér KUN JSON:

{
  "name": "",
  "details": "",
  "is_design": true/false,
  "confidence": 0.0
}

KRAV:
- vær specifik (ikke bare "stol")
- hvis design → skriv "muligvis [brand]"
"""

    models = ["gemini-2.5-flash", "gemini-2.5-pro"]

    for model in models:
        result = call_gemini(prompt, image_base64, model)
        if result:
            return result
        time.sleep(1)

    return None


# ---------- STEP 2: PRICING ----------
def price_object(image_base64, identity_text):

    prompt = f"""
Du vurderer pris på brugt genstand i Danmark.

Produkt:
{identity_text}

Returnér KUN JSON:

{{
  "price_min": 0,
  "price_max": 0,
  "confidence": 0.0
}}

Regler:
- hvis design → højere pris
- snævert interval
"""

    models = ["gemini-2.5-flash", "gemini-2.5-pro"]

    for model in models:
        result = call_gemini(prompt, image_base64, model)
        if result:
            return result
        time.sleep(1)

    return None


# ---------- PARSE ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())
    except:
        return {}


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1
    identity_raw = identify_object(base64_image)

    if not identity_raw:
        return {
            "description": "Kunne ikke analysere",
            "price_range": "-",
            "confidence": 0
        }

    identity = extract_json(identity_raw)

    # STEP 2
    price_raw = price_object(base64_image, identity.get("name", ""))

    if not price_raw:
        return {
            "description": identity.get("name", "ukendt"),
            "price_range": "-",
            "confidence": 0
        }

    price = extract_json(price_raw)

    price_min = int(price.get("price_min", 0))
    price_max = int(price.get("price_max", 0))

    return {
        "description": identity.get("name", "ukendt"),
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": int(price.get("confidence", 0) * 100)
    }


@app.get("/")
def root():
    return {"status": "ok"}