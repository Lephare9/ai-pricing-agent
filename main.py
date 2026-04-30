from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import os
import re
import json

app = FastAPI()

# 🌐 CORS (så frontend virker)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 API KEY
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------- AI ANALYSE ----------
def analyze_image_with_ai(image_bytes):
    try:
        prompt = """
Analyser billedet.

Du må KUN vurdere pris ud fra IDENTISKE eller næsten identiske produkter i Danmark.

Svar KUN med ren JSON (ingen tekst, ingen markdown):

{
  "name": "kort navn (1-3 ord)",
  "price": tal
}
"""

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=types.Content(
                role="user",
                parts=[
                    types.Part.from_text(prompt),
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg"
                    )
                ]
            )
        )

        return response.text

    except Exception as e:
        print("AI FEJL:", str(e))
        return '{"name": "ukendt", "price": 0}'


# ---------- JSON PARSER ----------
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

    try:
        ai_response = analyze_image_with_ai(image_bytes)
        print("AI RESPONSE:", ai_response)  # debug

        data = extract_json(ai_response)

        return {
            "description": data.get("name", "ukendt"),
            "price": data.get("price", 0)
        }

    except Exception as e:
        print("FEJL:", str(e))
        return {
            "description": "ukendt",
            "price": 0
        }


# ---------- TEST ----------
@app.get("/")
def root():
    return {"status": "API is running"}