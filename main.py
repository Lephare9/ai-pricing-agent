print("🔥 GEMINI FINAL STABLE AGENT 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import json
import base64
import requests

app = FastAPI()

# 🌐 CORS
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
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={GEMINI_API_KEY}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": """
Return ONLY valid JSON.

{
  "name": "product name",
  "price_min": number,
  "price_max": number,
  "hits_total": number,
  "hits_exact": number,
  "hits_similar": number,
  "confidence": number
}

Rules:
- Used prices in Denmark (DKK)
- Always include all fields
"""
                        },
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

        print("🔥 RAW API RESPONSE:", data)

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text

    except Exception as e:
        print("🔥 GEMINI ERROR:", str(e))
        return ""


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)

        if match:
            parsed = json.loads(match.group())
            print("🔥 PARSED JSON:", parsed)
            return parsed

    except Exception as e:
        print("🔥 JSON ERROR:", str(e))

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
    print("🔥 ENDPOINT HIT")

    image_bytes = await file.read()
    print("🔥 IMAGE SIZE:", len(image_bytes))

    ai_response = analyze_image(image_bytes)
    data = extract_json(ai_response)

    result = {
        "description": data.get("name", "ukendt"),
        "price_range": f"{data.get('price_min',0)} - {data.get('price_max',0)} kr",
        "hits_total": data.get("hits_total", 0),
        "hits_exact": data.get("hits_exact", 0),
        "hits_similar": data.get("hits_similar", 0),
        "confidence": data.get("confidence", 0)
    }

    print("🔥 FINAL RESPONSE:", result)

    return result


@app.get("/")
def root():
    return {"status": "ok"}