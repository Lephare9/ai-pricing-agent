
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google import genai
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
from google.genai import types

def analyze_image_with_ai(image_bytes):
    try:
        prompt = """
Analyser billedet og vurder en realistisk brugtpris.

Svar KUN i JSON:
{"name":"...", "price":123}
"""

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=types.Content(
                role="user",
                parts=[
                    types.Part(text=prompt),
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg"
                    )
                ]
            )
        )

        text = ""

        if response.candidates:
            parts = response.candidates[0].content.parts
            for p in parts:
                if hasattr(p, "text") and p.text:
                    text += p.text

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
    except:
        pass

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


@app.get("/")
def root():
    return {"status": "ok"}