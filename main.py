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


# ---------- GEMINI CALL (RETRY) ----------
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

    for i in range(2):  # 🔥 retry 1 gang
        try:
            res = requests.post(url, json=payload, timeout=20)
            data = res.json()

            if "candidates" not in data:
                print("NO CANDIDATES:", data)
                time.sleep(1)
                continue

            return data["candidates"][0]["content"]["parts"][0]["text"]

        except Exception as e:
            print("GEMINI ERROR:", e)
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


# ---------- STEP 1 ----------
def identify_object(image_base64):

    prompt = """
Identificér objektet præcist.

Returnér KUN JSON:

{
  "name": "",
  "confidence": 0.0
}

Regler:
- nævn brand hvis muligt
- max 1 linje
"""

    return call_gemini(prompt, image_base64)


# ---------- STEP 2 ----------
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
- max 30% interval
"""

    return call_gemini(prompt, image_base64)


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1
    identity_raw = identify_object(base64_image)
    identity = extract_json(identity_raw) if identity_raw else {}

    name = identity.get("name") or "Ukendt produkt"

    # STEP 2
    price_raw = price_object(base64_image, name)
    price = extract_json(price_raw) if price_raw else {}

    price_min = int(price.get("price_min") or 0)
    price_max = int(price.get("price_max") or 0)

    # 🔥 fallback hvis AI fejler
    if price_min == 0 and price_max == 0:
        price_min = 200
        price_max = 800

    return {
        "description": name,
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": int((price.get("confidence") or 0) * 100)
    }


@app.get("/")
def root():
    return {"status": "ok"}