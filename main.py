print("🔥 GEMINI ONLY AGENT 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import json
import base64
from google import genai

# 🔑 Gemini client (NY SDK)
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

        Return ONLY valid JSON:

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
        - Estimate USED market prices in Denmark (DKK)
        - Be realistic
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

        return response.text

    except Exception as e:
        print("🔥 GEMINI ERROR:", str(e))
        return '{"name":"ukendt","price_min":0,"price_max":0,"hits_total":0,"hits_exact":0,"hits_similar":0,"confidence":0}'


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print("🔥 JSON FEJL:", str(e))

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

    ai_response = analyze_image(image_bytes)
    data = extract_json(ai_response)

    return {
        "description": data.get("name", "ukendt"),
        "price_range": f"{data.get('price_min',0)} - {data.get('price_max',0)} kr",
        "hits_total": data.get("hits_total", 0),
        "hits_exact": data.get("hits_exact", 0),
        "hits_similar": data.get("hits_similar", 0),
        "confidence": data.get("confidence", 0)
    }


# ---------- TEST ----------
@app.get("/")
def root():
    return {"status": "ok"}