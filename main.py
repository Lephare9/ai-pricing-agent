print("🔥 GEMINI STABLE AGENT V3 🔥")

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


# ---------- AI ----------
def analyze_image(image_bytes):
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = """
Du analyserer en brugt genstand i Danmark.

MÅL:
Identificér brand/model og giv realistisk pris.

KRITISK:
- Samme input skal give samme output (minimér variation)
- Undgå tilfældige forskelle i pris og antal hits

TRIN 1:
- Identificér kategori + brand + model hvis muligt
- Hvis designprodukt → vær præcis

TRIN 2:
- Må IKKE default til IKEA/JYSK uden tydelige tegn

TRIN 3:
- Vurder kvalitet (materiale, alder, stand)

TRIN 4 – PRIS:
- Brug danske markedspladser:
  DBA, Facebook Marketplace, Trendsales
- Brug både SOLGTE og AKTIVE priser

- Hvis model er genkendt:
  → brug KUN identiske produkter

- Hvis ikke:
  → brug lignende produkter

- Returnér SNÆVERT interval (max ±25%)

TRIN 5:
- hits_total
- hits_exact
- hits_similar

REGLER:
- Vær konservativ
- Undgå store udsving
- Vælg stabilt estimat fremfor aggressivt

OUTPUT (JSON):
{
  "name": "",
  "price_min": 0,
  "price_max": 0,
  "hits_total": 0,
  "hits_exact": 0,
  "hits_similar": 0,
  "confidence": 0.0
}
"""

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
            ]
        }]
    }

    res = requests.post(url, json=payload)
    data = res.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return text


# ---------- STABILISERING ----------
def stabilize_price(min_p, max_p):
    avg = (min_p + max_p) / 2

    # afrund til pæne tal
    avg = round(avg / 50) * 50

    return int(avg * 0.85), int(avg * 1.15)


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group())

        min_p = data.get("price_min", 0)
        max_p = data.get("price_max", 0)

        # 🔥 stabilisering
        min_p, max_p = stabilize_price(min_p, max_p)

        return {
            "name": data.get("name", "ukendt"),
            "price_min": min_p,
            "price_max": max_p,
            "hits_total": data.get("hits_total", 0),
            "hits_exact": data.get("hits_exact", 0),
            "hits_similar": data.get("hits_similar", 0),
            "confidence": data.get("confidence", 0)
        }

    except:
        return {
            "name": "ukendt",
            "price_min": 0,
            "price_max": 0,
            "hits_total": 0,
            "hits_exact": 0,
            "hits_similar": 0,
            "confidence": 0
        }


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    ai_text = analyze_image(image_bytes)
    data = extract_json(ai_text)

    return {
        "description": data["name"],
        "price_range": f"{data['price_min']} - {data['price_max']} kr",
        "hits_total": data["hits_total"],
        "hits_exact": data["hits_exact"],
        "hits_similar": data["hits_similar"],
        "confidence": int(data["confidence"] * 100)
    }


@app.get("/")
def root():
    return {"status": "ok"}