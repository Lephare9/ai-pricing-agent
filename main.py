print("🔥 GEMINI V4 DESIGN AGENT 🔥")

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

DIT PRIMÆRE MÅL:
Identificér om dette er et DESIGNERPRODUKT eller masseproduceret.

TRIN 1 – DESIGN DETECTION:
- Materialer (massivt træ, læder, metal vs plastik)
- Konstruktion (detaljer, håndværk)
- Form (unik vs standard)

Hvis høj kvalitet → design_possible = true

TRIN 2 – IDENTITET:
Hvis design_possible:
- Forsøg brand/model (fx Mater, Hay, Normann)

TRIN 3 – PRIS:
Hvis design:
- Brug high-end marked
- IGNORÉR IKEA/JYSK

Hvis ikke:
- Brug normal brugtpris

TRIN 4:
- Snævert interval (max ±25%)

OUTPUT JSON:
{
  "name": "",
  "price_min": 0,
  "price_max": 0,
  "hits_total": 0,
  "hits_exact": 0,
  "hits_similar": 0,
  "confidence": 0.0,
  "design_detected": true
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

    print("🔥 RAW:", data)

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return text


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group())

        # 🔥 DESIGN BOOST
        if data.get("design_detected") == True:
            data["price_min"] = int(data["price_min"] * 1.15)
            data["price_max"] = int(data["price_max"] * 1.25)

        return data

    except Exception as e:
        print("🔥 JSON ERROR:", e)

        return {
            "name": "ukendt",
            "price_min": 0,
            "price_max": 0,
            "hits_total": 0,
            "hits_exact": 0,
            "hits_similar": 0,
            "confidence": 0,
            "design_detected": False
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