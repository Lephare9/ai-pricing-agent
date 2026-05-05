from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, re

app = FastAPI()

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


@app.get("/")
def root():
    return {"status": "ok - v17.1 AI-first"}


# ---------- AI BESKRIVELSE ----------
def describe(img64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = """Svar på dansk.

Beskriv objektet kort og præcist med:
- type
- materiale
- farve
- form

Eksempel:
"keramisk bordlampe med beige stofskærm og rund fod"

Ingen forklaring.
"""

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img64}}
            ]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=15)

        print("DESC STATUS:", r.status_code)

        if r.status_code != 200:
            return "ukendt objekt"

        data = r.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"]

        txt = txt.lower().strip()
        txt = re.sub(r"[^\w\sæøå]", "", txt)

        print("DESC:", txt)

        return txt

    except Exception as e:
        print("DESC ERROR:", e)
        return "ukendt objekt"


# ---------- AI PRIS ----------
def ai_price(desc):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
Du er ekspert i brugtpriser i Danmark.

Vurder realistisk pris på:
{desc}

Svar kun med ét tal i danske kroner.
Ingen forklaring.
"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=12)

        print("PRICE STATUS:", r.status_code)

        if r.status_code != 200:
            return None

        data = r.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"]

        match = re.findall(r"\d+", txt)

        if match:
            val = int(match[0])
            print("AI PRICE:", val)
            return val

        return None

    except Exception as e:
        print("PRICE ERROR:", e)
        return None


# ---------- STAND / NOTE ----------
def generate_note(desc):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
Giv en MEGET kort vurdering af stand for:
{desc}

Eksempler:
"middel stand"
"små brugsspor"
"god stand"

Kun 2-4 ord.
"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=10)

        if r.status_code != 200:
            return "middel stand"

        data = r.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"]

        txt = txt.lower().strip()
        txt = re.sub(r"[^\w\sæøå ]", "", txt)

        return txt

    except:
        return "middel stand"


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()

    if not img:
        return {
            "description": "-",
            "price": "-",
            "note": "fejl"
        }

    img64 = base64.b64encode(img).decode("utf-8")

    # 🔥 BESKRIVELSE
    desc = describe(img64)

    # 🔥 PRIS (ALTID)
    price = ai_price(desc)

    if not price:
        price = 200  # sidste fallback (aldrig tom)

    # 🔥 NOTE
    note = generate_note(desc)

    return {
        "description": desc,
        "price": f"{price} kr",
        "note": note
    }