from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests

# ---------- APP ----------
app = FastAPI()

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- ENV ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print("STARTING APP...")
print("HAS GEMINI KEY:", bool(GEMINI_API_KEY))


# ---------- ROOT ----------
@app.get("/")
def root():
    return {"status": "ok - v2"}


# ---------- TEST ENDPOINT ----------
@app.get("/ping")
def ping():
    return {"ping": "pong"}


# ---------- GEMINI ----------
def call_gemini(image_base64):

    if not GEMINI_API_KEY:
        print("NO GEMINI KEY")
        return None

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": "Describe this object shortly"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                }
            ]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=15)

        print("GEMINI STATUS:", r.status_code)
        print("GEMINI RESPONSE:", r.text[:300])

        if r.status_code != 200:
            return None

        data = r.json()

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        print("GEMINI ERROR:", str(e))
        return None


# ---------- ANALYZE ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    print("REQUEST RECEIVED")

    img = await file.read()

    print("IMAGE SIZE:", len(img))

    if not img:
        return {
            "description": "ingen fil",
            "price_range": "ingen pris"
        }

    img64 = base64.b64encode(img).decode("utf-8")

    result = call_gemini(img64)

    if result is None:
        return {
            "description": "ukendt produkt",
            "price_range": "ingen pris"
        }

    return {
        "description": result,
        "price_range": "test ok"
    }