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

    try:
        res = requests.post(url, json=payload, timeout=25)
        data = res.json()

        if "candidates" not in data:
            print("NO CANDIDATES:", data)
            return None

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        print("GEMINI ERROR:", e)
        return None


# ---------- STEP 1: IDENTIFY ----------
def identify_object(image_base64):

    prompt = """
Identificér objektet meget præcist.

Returnér KUN JSON:

{
  "name": "",
  "confidence": 0.0
}

Regler:
- nævn brand hvis muligt
- kort tekst (max 1 linje)
"""

    return call_gemini(prompt, image_base64)


# ---------- STEP 2: PRICE ----------
def price_object(image_base64, name):

    prompt = f"""
Vurder brugtpris i Danmark.

Produkt: {name}

Returnér KUN JSON:

{{
  "price_min": 0,
  "price_max": 0,
  "confidence": 0.0
}}

Regler:
- realistisk DBA niveau
- snævert interval
"""

    return call_gemini(prompt, image_base64)


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

    try:
        image_bytes = await file.read()

        if not image_bytes:
            return {"error": "no image"}

        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # STEP 1
        identity_raw = identify_object(base64_image)

        if not identity_raw:
            return {"error": "identify failed"}

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

        return {
            "description": identity.get("name", "ukendt"),
            "price_range": f"{int(price.get('price_min',0))} - {int(price.get('price_max',0))} kr",
            "confidence": int(price.get("confidence", 0) * 100)
        }

    except Exception as e:
        print("SERVER ERROR:", e)
        return {"error": "server crash"}


@app.get("/")
def root():
    return {"status": "ok"}