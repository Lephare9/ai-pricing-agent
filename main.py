print("🔥 GEMINI V7 STABLE 🔥")

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

        print(f"\n🔥 MODEL {model} RESPONSE:\n", data)

        if "candidates" not in data:
            return None

        text = data["candidates"][0]["content"]["parts"][0].get("text", "")

        if not text or "{" not in text:
            return None

        return text

    except Exception as e:
        print("🔥 GEMINI ERROR:", e)
        return None


# ---------- PARSE ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*?\}", text, re.DOTALL)  # ✅ non-greedy
        return json.loads(match.group())
    except Exception as e:
        print("🔥 JSON ERROR:", text)
        return {}


# ---------- STEP 1 ----------
def identify_object(image_base64):

    prompt = """
Du analyserer et billede.

Returnér KUN JSON:

{
  "name": "",
  "details": "",
  "is_design": true/false,
  "confidence": 0.0
}

KRAV:
- vær specifik (ikke "stol")
- hvis muligt → brand/model
"""

    models = ["gemini-2.5-pro", "gemini-2.5-flash"]

    for model in models:
        result = call_gemini(prompt, image_base64, model)
        if result:
            parsed = extract_json(result)
            if parsed.get("name"):
                return parsed
        time.sleep(1)

    return None


# ---------- STEP 2 ----------
def price_object(image_base64, identity_json):

    prompt = f"""
Du vurderer pris på brugt genstand i Danmark.

Produkt:
{identity_json}

Returnér KUN JSON:

{{
  "price_min": 0,
  "price_max": 0,
  "confidence": 0.0
}}

Regler:
- snævert interval
- realistisk DBA/Marketplace pris
"""

    models = ["gemini-2.5-pro", "gemini-2.5-flash"]

    for model in models:
        result = call_gemini(prompt, image_base64, model)
        if result:
            parsed = extract_json(result)
            if parsed.get("price_max", 0) > 0:
                return parsed
        time.sleep(1)

    return None


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1
    identity = identify_object(base64_image)

    if not identity:
        return {
            "description": "Kunne ikke analysere",
            "price_range": "-",
            "confidence": 0
        }

    # STEP 2 (🔥 FIX: send hele JSON)
    price = price_object(base64_image, json.dumps(identity))

    if not price:
        return {
            "description": identity.get("name", "ukendt"),
            "price_range": "-",
            "confidence": 0
        }

    return {
        "description": identity.get("name", "ukendt"),
        "price_range": f"{int(price.get('price_min',0))} - {int(price.get('price_max',0))} kr",
        "confidence": int(price.get("confidence", 0) * 100)
    }


@app.get("/")
def root():
    return {"status": "ok"}