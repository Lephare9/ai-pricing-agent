from fastapi import FastAPI, UploadFile, File
from google import genai
import os
import re

app = FastAPI()

# 🔑 API KEY fra Render environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------- AI ANALYSE ----------
def analyze_image_with_ai(image_bytes):
    prompt = """
Analyser billedet.

Du må KUN vurdere pris ud fra IDENTISKE eller næsten identiske produkter i Danmark.

Svar KUN i JSON:
{
  "name": "1-3 ord produktnavn",
  "price": tal
}

Regler:
- realistisk brugtpris
- ignorér outliers
- ingen forklaring
"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=[
            prompt,
            {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
        ]
    )

    return response.text


# ---------- JSON PARSER ----------
def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return eval(match.group())
    except:
        pass
    return {"name": "ukendt", "price": 0}


# ---------- API ENDPOINT ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    try:
        ai_response = analyze_image_with_ai(image_bytes)
        data = extract_json(ai_response)

        return {
            "description": data.get("name", "ukendt"),
            "price": data.get("price", 0)
        }

    except Exception as e:
        print("FEJL:", e)

        return {
            "description": "ukendt",
            "price": 0
        }