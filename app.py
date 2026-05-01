from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import os
import re
import json

# 🔥 init
app = FastAPI()

# 🌐 CORS (frontend adgang)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ---------- AI ----------
def analyze_image_with_ai(image_bytes):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = """
Returnér KUN gyldig JSON.

Format:
{"name":"kort navn","price":123}

Regler:
- Ingen tekst før eller efter JSON
- price skal være et tal (ingen "kr")
- realistisk brugtpris i Danmark
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
        print("RAW:", text)

        text = text.replace("```json", "").replace("```", "")

        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())

            # 🔥 hvis price er string → gør til int
            if isinstance(data.get("price"), str):
                data["price"] = int(re.sub(r"\D", "", data["price"]) or 0)

            return data

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