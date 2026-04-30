from fastapi import FastAPI, UploadFile, File
from google import genai
import re
import time

app = FastAPI()

# 🔑 DIN API KEY
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------- AI CALL MED RETRY + FALLBACK ----------
def call_ai_with_retry(image_bytes):
    models = [
        "gemini-3.1-flash-lite-preview",     # primær (hurtig)
        "gemini-3.1-flash-image-preview"     # fallback
    ]

    prompt = """
Analyser billedet.

Du må KUN vurdere pris ud fra IDENTISKE eller næsten identiske produkter.

Svar KUN i JSON:
{
  "name": "1-3 ord produktnavn",
  "price": tal
}

Regler:
- realistisk brugtpris i Danmark
- ignorér afvigelser og design-varianter
- ingen forklaring
"""

    for model in models:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        genai.types.Part.from_bytes(
                            data=image_bytes,
                            mime_type="image/jpeg"
                        )
                    ]
                )

                return response.text

            except Exception as e:
                print(f"AI fejl ({model}) forsøg {attempt+1}:", e)
                time.sleep(1)  # lille pause før retry

    return None


# ---------- PARSE AI SVAR ----------
def parse_ai_response(text):
    if not text:
        return "ukendt", None

    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
    name = name_match.group(1) if name_match else "ukendt"

    price_match = re.search(r'"price"\s*:\s*(\d+)', text)
    price = int(price_match.group(1)) if price_match else None

    return name, price


# ---------- ROOT ----------
@app.get("/")
def root():
    return {"status": "AI robust mode kører"}


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    raw = call_ai_with_retry(image_bytes)

    name, price = parse_ai_response(raw)

    return {
        "description": name,
        "price": price,
        "raw": raw
    }