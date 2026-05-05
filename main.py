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
  "brand": ""
}

Regler:
- vær konkret
- find model hvis muligt
"""

    return call_gemini(prompt, image_base64)


# ---------- STEP 2: GENERATE PRICE LIST ----------
def generate_price_list(name, brand):

    prompt = f"""
Find 8-15 realistiske brugtpriser i Danmark.

Produkt: {name}
Brand: {brand}

REGLER:
- basér på DBA / marketplace niveau
- brug både solgte og til salg
- hvis ukendt brand → brug lignende produkter
- hvis kendt brand → brug identiske
- undgå ekstreme outliers

Returnér KUN JSON:

{{
  "prices": [100,150,200,250],
  "confidence": 0.0
}}
"""

    return call_gemini(prompt)


# ---------- PRICE CALC ----------
def compute_price(prices, brand):

    if not prices or len(prices) < 3:
        return 100, 400, 50  # fallback (sjældent)

    avg = sum(prices) / len(prices)

    if brand.lower() != "ukendt":
        spread = 0.25
        confidence = 80
    else:
        spread = 0.15
        confidence = 65

    price_min = int(avg * (1 - spread))
    price_max = int(avg * (1 + spread))

    return price_min, price_max, confidence


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

    # STEP 2
    price_raw = generate_price_list(name, brand)
    price_data = extract_json(price_raw) if price_raw else {}

    prices = price_data.get("prices", [])
    confidence_ai = int((price_data.get("confidence") or 0) * 100)

    # STEP 3
    price_min, price_max, confidence_calc = compute_price(prices, brand)

    confidence = max(confidence_ai, confidence_calc)

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": confidence
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v6-market-sim"}