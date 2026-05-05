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


# ---------- GEMINI CALL (STABIL + RETRY) ----------
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


# ---------- ROBUST JSON PARSER ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        print("JSON ERROR:", text)
        return {}


# ---------- STEP 1: IDENTIFY (BRAND OPTIMERET) ----------
def identify_object(image_base64):

    prompt = """
Analyser billedet og identificér produktet præcist.

Returnér KUN JSON:

{
  "name": "",
  "brand": "",
  "details": "",
  "confidence": 0.0
}

KRAV:
- find specifik model hvis muligt
- find brand (Bolia, HAY, IKEA, Mater, Muuto, Fritz Hansen, Normann osv)
- hvis usikker → skriv "ukendt"
- max 5 linjer i details
- vær konkret, ikke generisk
"""

    return call_gemini(prompt, image_base64)


# ---------- STEP 2: PRICE (BRAND AWARE) ----------
def price_object(image_base64, name, brand):

    prompt = f"""
Vurder brugtpris i Danmark.

Produkt: {name}
Brand: {brand}

Returnér KUN JSON:

{{
  "price_min": 0,
  "price_max": 0,
  "confidence": 0.0
}}

REGLER:
- design brands = højere pris (Bolia, HAY, Mater, Muuto, Fritz Hansen)
- IKEA = lavere pris
- realistisk DBA niveau
- max 25% interval
- hvis model kendes → vær præcis
- hvis ukendt → lav konservativ vurdering
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
    brand = identity.get("brand") or "ukendt"
    details = identity.get("details") or ""

    # STEP 2
    price_raw = price_object(base64_image, name, brand)
    price = extract_json(price_raw) if price_raw else {}

    price_min = int(price.get("price_min") or 0)
    price_max = int(price.get("price_max") or 0)

    # 🔥 fallback hvis AI fejler
    if price_min == 0 and price_max == 0:
        if brand.lower() in ["bolia", "hay", "mater", "muuto"]:
            price_min, price_max = 1500, 3500
        else:
            price_min, price_max = 200, 800

    confidence = int((price.get("confidence") or 0) * 100)

    return {
        "description": f"{name}\n{brand}\n{details}",
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": confidence
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "brand-optimized"}