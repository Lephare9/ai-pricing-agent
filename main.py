print("🔥 HTTP VERSION ACTIVE 🔥")

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

# ---------- AI ----------
def analyze_image_with_ai(image_bytes):
    print("🔥 FUNCTION STARTED")

    try:
        prompt = """Returnér KUN JSON:
{"name":"kort navn","price":123}
"""

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        print("🔥 CALLING AI (HTTP)...")

        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-vision:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": os.getenv("GEMINI_API_KEY")},
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": image_base64
                                }
                            }
                        ]
                    }
                ]
            }
        )

        data = response.json()
        print("🔥 RAW RESPONSE:", data)

        text = data.get("candidates", [{}])[0] \
                  .get("content", {}) \
                  .get("parts", [{}])[0] \
                  .get("text", "")

        print("🔥 AI RAW:", text)

        return text if text else '{"name":"ukendt","price":0}'

    except Exception as e:
        print("🔥 AI FEJL:", str(e))
        return '{"name":"ukendt","price":0}'


# ---------- JSON ----------
def extract_json(text):
    try:
        print("🔥 PARSER INPUT:", text)

        text = text.replace("```json", "").replace("```", "")

        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())

            if isinstance(data.get("price"), str):
                data["price"] = int(re.sub(r"\D", "", data["price"]) or 0)

            print("🔥 PARSED JSON:", data)
            return data

    except Exception as e:
        print("🔥 JSON FEJL:", str(e))

    return {"name": "ukendt", "price": 0}


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("🔥 ENDPOINT HIT")

    image_bytes = await file.read()
    print("🔥 FILE RECEIVED:", len(image_bytes), "bytes")

    ai_response = analyze_image_with_ai(image_bytes)
    data = extract_json(ai_response)

    print("🔥 FINAL OUTPUT:", data)

    return {
        "description": data.get("name", "ukendt"),
        "price": data.get("price", 0)
    }


# ---------- TEST ----------
@app.get("/")
def root():
    return {"status": "ok"}