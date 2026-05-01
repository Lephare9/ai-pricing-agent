from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import os
import re
import json



app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ---------- AI ----------
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def analyze_image_with_ai(image_bytes):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = """
Returnér KUN JSON:
{"name":"kort navn","price":123}
"""

        response = model.generate_content(
            [
                prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]
        )

        text = response.text

        print("AI RAW:", text)

        return text if text else '{"name":"ukendt","price":0}'

    except Exception as e:
        print("AI FEJL:", str(e))
        return '{"name":"ukendt","price":0}'


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "")
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print("JSON FEJL:", str(e))

    return {"name": "ukendt", "price": 0}


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    ai_response = analyze_image_with_ai(image_bytes)
    data = extract_json(ai_response)

    return {
        "description": data.get("name", "ukendt"),
        "price": data.get("price", 0)
    }


# ---------- TEST ----------
@app.get("/")
def root():
    return {"status": "ok"}