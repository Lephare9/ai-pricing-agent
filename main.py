import os
import io
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from google import genai
from google.genai import types

print("🔥 AI PRICING AGENT v19 🔥")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("🔑 GEMINI:", "OK" if GEMINI_API_KEY else "MISSING")

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROOT ---
@app.get("/")
def root():
    return {"status": "ok", "version": "v19"}


# --- MODELS DEBUG ---
@app.get("/models")
def list_models():
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = client.models.list()
        return {"models": [m.name for m in models]}
    except Exception as e:
        return {"error": str(e)}


# --- ANALYZE ---
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    try:
        contents = await file.read()
        print("📷 SIZE:", len(contents))

        # --- compress image ---
        from PIL import Image

        image = Image.open(io.BytesIO(contents))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=60)
        image_bytes = buffer.getvalue()

        print("📦 COMPRESSED:", len(image_bytes))

        # --- Gemini client ---
        client = genai.Client(api_key=GEMINI_API_KEY)

        # --- Gemini call (KORREKT FORMAT) ---
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[
                "Hvad er dette objekt? Svar kort.",
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg"
                )
            ]
        )

        result_text = (response.text or "").strip()
        print("🧠 GEMINI:", result_text)

        if not result_text:
            return {
                "name": "Ingen analyse",
                "price": 0
            }

        return {
            "name": result_text,
            "price": 100
        }

    except Exception as e:
        print("🚨 FEJL:", str(e))
        return {
            "name": "Fejl",
            "price": 0,
            "error": str(e)
        }