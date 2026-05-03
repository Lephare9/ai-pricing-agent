print("🔥 GEMINI DEBUG AGENT 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import json
import base64
from google import genai

# 🔑 Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
def analyze_image(image_bytes):
    try:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = """
        Analyze this item from an image.

        IMPORTANT:
        Return ONLY valid JSON. No text before or after.

        Example:
        {
          "name": "iPhone 12",
          "price_min": 1500,
          "price_max": 2500,
          "hits_total": 5,
          "hits_exact": 3,
          "hits_similar": 2,
          "confidence": 80
        }

        Rules:
        - Danish used market prices (DKK)
        - Always include ALL fields
        """

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                }
            ]
        )

        text = response.text
        print("🔥 GEMINI RAW RESPONSE:", text)

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
            data = json.loads(match.group())
            print("🔥 PARSED JSON:", data)
            return data

    except Exception as e:
        print("🔥 JSON ERROR:", str(e))

    # fallback
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


# ---------- TEST ----------
@app.get("/")
def root():
    return {"status": "ok"}