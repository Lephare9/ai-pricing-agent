print("🔥 GEMINI V2.1 AGENT 🔥")

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

TRIN 1:
- Identificér kategori + brand + model hvis muligt
- Hvis designprodukt → vær specifik

TRIN 2:
- Må IKKE default til IKEA/JYSK uden grund

TRIN 3:
- Vurder kvalitet (materialer, finish)

TRIN 4 – PRIS:
- Brug SOLGTE + AKTIVE annoncer
- Hvis model genkendt → brug KUN identiske
- Ellers → brug lignende

- Giv SNÆVERT interval (max ±25%)

TRIN 5:
- hits_total
- hits_exact
- hits_similar

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


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group())

        # smart price logic
        if data.get("hits_exact", 0) > 0:
            pass
        else:
            data["price_min"] = int(data["price_min"] * 0.9)
            data["price_max"] = int(data["price_max"] * 1.1)

        return data

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