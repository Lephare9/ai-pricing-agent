import os
import io
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from google import genai
from google.genai import types

print("🔥 AI PRICING AGENT v18 🔥")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("🔑 GEMINI:", "OK" if GEMINI_API_KEY else "MISSING")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "ok", "version": "v18"}


# ---------------- LIST MODELS ----------------
@app.get("/models")
def list_models():
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = client.models.list()

        result = []
        for m in models:
            result.append(m.name)

        print("📦 MODELS:", result)

        return {"models": result}

    except Exception as e:
        print("🚨 MODEL LIST FEJL:", str(e))
        return {"error": str(e)}


# ---------------- GEMINI CALL ----------------
def call_gemini(client, image_bytes):
    test_models = [
        "models/gemini-1.5-flash-latest",
        "models/gemini-1.5-flash",
        "models/gemini-1.5-pro",
        "models/gemini-1.0-pro"
    ]

    for model in test_models:
        try:
            print("⚡ TRY MODEL:", model)

            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(text="Hvad er dette objekt? Svar kort."),
                            types.Part(
                                inline_data=types.Blob(
                                    mime_type="image/jpeg",
                                    data=image_bytes
                                )
                            )
                        ]
                    )
                ]
            )

            text = (response.text or "").strip()
            print("🧠 GEMINI:", text)

            if text:
                return text

        except Exception as e:
            print("❌ FAIL:", model, str(e))

    return None


# ---------------- ANALYZE ----------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    try:
        contents = await file.read()
        print("📷 SIZE:", len(contents))

        # compress
        from PIL import Image

        image = Image.open(io.BytesIO(contents))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=60)
        img = buf.getvalue()

        print("📦 COMPRESSED:", len(img))

        client = genai.Client(api_key=GEMINI_API_KEY)

        result = call_gemini(client, img)

        if not result:
            return {
                "name": "Ingen model virkede",
                "price": 0
            }

        return {
            "name": result,
            "price": 100
        }

    except Exception as e:
        print("🔥 CRASH:", str(e))
        return {
            "name": "Server fejl",
            "price": 0,
            "error": str(e)
        }