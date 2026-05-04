print("🔥 GEMINI V6 STABLE AGENT 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re, time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ---------- CALL GEMINI ----------
def call_gemini(image_base64, model):

    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": "Analyser produkt og returnér JSON med navn og pris"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                }
            ]
        }]
    }

    res = requests.post(url, json=payload, timeout=20)
    data = res.json()

    print(f"🔥 MODEL {model}:", data)

    if "candidates" not in data:
        return None

    return data["candidates"][0]["content"]["parts"][0]["text"]


# ---------- AI ----------
def analyze_image(image_bytes):
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # 🔁 retry + fallback
    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro"
    ]

    for i, model in enumerate(models):
        try:
            print(f"🔥 TRY {i+1} → {model}")

            result = call_gemini(base64_image, model)

            if result:
                return result

            time.sleep(1)

        except Exception as e:
            print("🔥 ERROR:", e)
            time.sleep(1)

    return None


# ---------- JSON ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group())

        return data

    except:
        return {
            "name": "ukendt",
            "price_min": 0,
            "price_max": 0,
            "confidence": 0
        }


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    ai_text = analyze_image(image_bytes)

    # 🔥 FAIL SAFE
    if not ai_text:
        return {
            "description": "AI er travl – prøv igen",
            "price_range": "-",
            "confidence": 0
        }

    data = extract_json(ai_text)

    return {
        "description": data.get("name", "ukendt"),
        "price_range": f"{int(data.get('price_min', 0))} - {int(data.get('price_max', 0))} kr",
        "confidence": int(data.get("confidence", 0) * 100)
    }


@app.get("/")
def root():
    return {"status": "ok"}