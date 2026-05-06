from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, re, statistics

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
SERP_API_KEY = os.getenv("SERP_API_KEY")


@app.get("/")
def root():
    return {"status": "ok - v17.2 SERP + AI"}


# ---------- AI BESKRIVELSE ----------
def describe(img64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = "Beskriv objektet kort på dansk med type, materiale og form."

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
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return txt.lower()

    except:
        return "ukendt objekt"


# ---------- SERP SEARCH ----------
def serp_prices(query):

    url = "https://serpapi.com/search.json"

    params = {
        "q": f"{query} dba brugt pris",
        "api_key": SERP_API_KEY,
        "hl": "da",
        "gl": "dk"
    }

    try:
        r = requests.get(url, params=params, timeout=10)

        print("SERP STATUS:", r.status_code)

        data = r.json()

        prices = []

        for res in data.get("organic_results", []):

            text = res.get("title", "") + " " + res.get("snippet", "")

            found = re.findall(r"\b\d{2,5}\b", text)

            for f in found:
                val = int(f)

                # filtrer støj
                if 50 < val < 50000:
                    prices.append(val)

        print("SERP PRICES:", prices)

        return prices

    except Exception as e:
        print("SERP ERROR:", e)
        return []


# ---------- AI FALLBACK ----------
def ai_price(desc):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"Vurder brugtpris i Danmark for: {desc}. Kun tal."

    try:
        r = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}]
        })

        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]

        match = re.search(r"\d+", txt)

        if match:
            return int(match.group())

    except:
        pass

    return 200


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()
    img64 = base64.b64encode(img).decode("utf-8")

    # 1. Beskrivelse
    desc = describe(img64)

    # 2. SERP priser
    prices = serp_prices(desc)

    if prices:
        price = int(statistics.median(prices))
        source = "serp"
    else:
        price = ai_price(desc)
        source = "ai"

    return {
        "description": desc,
        "price": f"{price} kr",
        "source": source
    }