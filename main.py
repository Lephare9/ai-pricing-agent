print("🔥 GEMINI V7 FINAL BRAND OPTIMIZED 🔥")

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


# ---------- CALL GEMINI (RETRY + TIMEOUT) ----------
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

    for attempt in range(2):  # retry
        try:
            res = requests.post(url, json=payload, timeout=60)
            data = res.json()

            if "candidates" not in data:
                continue

            text = data["candidates"][0]["content"]["parts"][0].get("text", "")

            if text and "{" in text:
                return text, None

        except Exception as e:
            print(f"TRY {attempt+1} FAILED:", e)

    return None, "timeout"


# ---------- PARSE ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        return json.loads(match.group()), None
    except:
        print("JSON ERROR:", text)
        return {}, "parse_error"


# ---------- STEP 1: IDENTIFY ----------
def identify_object(image_base64):

    prompt = """
Analyser billedet præcist.

Returnér KUN JSON:

{
  "name": "",
  "condition": "",
  "confidence": 0.0
}

KRAV:
- identificér brand og model hvis muligt
- hvis møbel: overvej kendte designbrands (fx HAY, Muuto, Mater, Fritz Hansen, Bolia)
- skriv brand hvis der er visuelle tegn
- undgå generiske svar
- max 1 kort linje
"""

    text, err = call_gemini(prompt, image_base64)
    if err:
        return None, err

    parsed, parse_err = extract_json(text)
    if parse_err:
        return None, parse_err

    name = parsed.get("name", "")
    confidence = parsed.get("confidence", 0)

    if not name:
        return None, "ai_failed"

    # 🔥 Stop generiske svar
    if len(name.split()) < 2:
        return None, "ai_failed"

    # 🔥 Anti IKEA fallback
    if "ikea" in name.lower() and confidence < 0.6:
        return None, "ai_failed"

    return parsed, None


# ---------- STEP 2: PRICE ----------
def price_object(identity_json):

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
- realistisk DBA niveau
- max 30-40% forskel
- undgå for lave priser på design
"""

    text, err = call_gemini(prompt, None)

    if err:
        return None, err

    parsed, parse_err = extract_json(text)
    if parse_err:
        return None, parse_err

    if parsed.get("price_max", 0) <= 0:
        return None, "ai_failed"

    return parsed, None


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1
    identity, err = identify_object(base64_image)
    if err:
        return {
            "description": "Ukendt model",
            "price_range": "-",
            "confidence": 0,
            "error": err
        }

    # STEP 2
    price, err = price_object(json.dumps(identity))
    if err:
        return {
            "description": identity.get("name", "Ukendt"),
            "price_range": "-",
            "confidence": 0,
            "error": err
        }

    price_min = int(price.get("price_min", 0))
    price_max = int(price.get("price_max", 0))

    name = identity.get("name", "").lower()

    # 🔥 Brand boost
    if any(x in name for x in ["mater", "hay", "fritz", "muuto", "bolia"]):
        price_min = int(price_min * 1.3)
        price_max = int(price_max * 1.3)

    # Mild clamp
    if price_max > 0:
        diff = price_max - price_min
        if diff > price_max * 0.5:
            mid = (price_min + price_max) // 2
            price_min = int(mid * 0.8)
            price_max = int(mid * 1.2)

    return {
        "description": identity.get("name", "Ukendt"),
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": int(price.get("confidence", 0) * 100),
        "error": None
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "mode": "brand-optimized"
    }
