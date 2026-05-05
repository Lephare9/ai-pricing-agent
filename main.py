from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, re

app = FastAPI()

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
    return {"status": "ok - v17"}


# ---------- AI BESKRIVELSE ----------
def describe(img64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """Svar på dansk.

Beskriv objektet præcist:
- type
- materiale
- farve
- form

Kort og konkret.

Eksempel:
"keramisk bordlampe med beige stofskærm og rund fod"
"""
                },
                {"inline_data": {"mime_type": "image/jpeg", "data": img64}}
            ]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=15)

        if r.status_code != 200:
            return None

        data = r.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"]

        txt = txt.lower().strip()
        txt = re.sub(r"[^\w\sæøå]", "", txt)

        print("DESC:", txt)

        return txt

    except Exception as e:
        print("DESC ERROR:", e)
        return None


# ---------- AI PRIS ----------
def ai_price(desc):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
Du er ekspert i brugtpriser i Danmark.

Vurder realistisk pris på:
{desc}

Svar kun med ét tal i kroner.
"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=10)

        if r.status_code != 200:
            return None

        data = r.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"]

        val = int(re.findall(r"\d+", txt)[0])

        print("AI PRICE:", val)

        return val

    except:
        return None


# ---------- BUILD SEARCH ----------
def build_queries(desc):

    return [
        desc,
        desc + " dba",
        desc + " til salg",
        desc + " danmark",
    ]


# ---------- SEARCH ----------
def search_prices(queries):

    prices = []

    for q in queries:

        params = {
            "q": q,
            "api_key": SERP_API_KEY,
            "hl": "da",
            "gl": "dk"
        }

        try:
            r = requests.get("https://serpapi.com/search", params=params, timeout=10)
            data = r.json()

            for res in data.get("organic_results", []):
                text = (res.get("title", "") + " " + res.get("snippet", "")).lower()

                found = re.findall(r"(\d{2,6})\s*kr", text)

                for f in found:
                    val = int(f)
                    if 20 < val < 100000:
                        prices.append(val)

        except Exception as e:
            print("SEARCH ERROR:", e)

    print("DATA PRICES:", prices)

    return prices


# ---------- CLEAN ----------
def clean(prices):

    if not prices:
        return []

    prices.sort()
    median = prices[len(prices)//2]

    return [p for p in prices if median * 0.3 < p < median * 3]


# ---------- CALC ----------
def calc(prices):

    if not prices:
        return None

    prices.sort()
    return prices[len(prices)//2]


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()

    if not img:
        return {"description": "-", "price": "-", "note": "fejl"}

    img64 = base64.b64encode(img).decode("utf-8")

    # 🔥 1. BESKRIVELSE
    desc = describe(img64)

    if not desc:
        desc = "ukendt objekt"

    # 🔥 2. DATA SEARCH
    queries = build_queries(desc)
    prices = search_prices(queries)
    prices = clean(prices)

    data_price = calc(prices)

    # 🔥 3. AI FALLBACK
    ai_est = ai_price(desc)

    # 🔥 4. FINAL LOGIK
    if data_price:
        final = data_price
        note = "baseret på lignende fund"
    elif ai_est:
        final = ai_est
        note = "AI vurdering (ingen fund)"
    else:
        final = "ukendt"
        note = "ingen data"

    return {
        "description": desc,
        "price": f"{final} kr" if isinstance(final, int) else final,
        "note": note,
        "data_points": len(prices)
    }