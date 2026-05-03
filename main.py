print("🔥 GEMINI OPTIMIZED AGENT 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os
import base64
import requests
import json
import re

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
Du vurderer brugtpris på danske genbrugsvarer.

KRAV:
- Kun danske markedspriser (DBA, Facebook Marketplace, Trendsales)
- KUN brugte varer (ikke nypris)
- Vurder realistisk salgspris (ikke ønsket pris)

PRIS:
- Giv et SNÆVERT interval (max ±30%)
- Hvis usikker → reducer interval
- Undgå brede ranges

OUTPUT (kun JSON):
{
  "name": "kort dansk navn",
  "price_min": 100,
  "price_max": 200,
  "hits_total": 50,
  "hits_exact": 10,
  "hits_similar": 40,
  "confidence": 0.0-1.0
}
"""

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_image
                        }
                    }
                ]
            }
        ]
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

        # clamp range
        if data["price_max"] > data["price_min"] * 1.6:
            avg = (data["price_min"] + data["price_max"]) // 2
            data["price_min"] = int(avg * 0.8)
            data["price_max"] = int(avg * 1.2)

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