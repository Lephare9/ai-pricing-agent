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
SERP_API_KEY = os.getenv("SERP_API_KEY")


@app.get("/")
def root():
    return {"status": "ok - v16.2"}


# ---------- GEMINI (DETALJERET BESKRIVELSE) ----------
def identify(img64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """Svar på dansk.

Beskriv objektet kort og præcist med:
- type
- materiale
- farve
- form

Eksempel:
"keramisk bordlampe med hvid stofskærm og rund base"

Ingen forklaring."""
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
        print("AI ERROR:", e)
        return None


# ---------- BUILD QUERIES ----------
def build_queries(desc):

    return [
        desc,
        desc + " lampe" if "lampe" not in desc else desc,
        desc + " dba",
        desc + " til salg",
        desc + " danmark"
    ]


# ---------- SEARCH (FIXED) ----------
def search_prices(queries):

    prices = []

    for q in queries:

        print("SEARCH:", q)

        params = {
            "q": q,
            "api_key": SERP_API_KEY,
            "engine": "google",
            "hl": "da",
            "gl": "dk"
        }

        try:
            r = requests.get("https://serpapi.com/search", params=params, timeout=10)
            data = r.json()

            # 🔥 SHOPPING RESULTS (bedste)
            for item in data.get("shopping_results", []):
                price_str = item.get("price", "")

                match = re.findall(r"(\d+)", price_str.replace(".", ""))
                for m in match:
                    val = int(m)
                    if 20 < val < 100000:
                        prices.append(val)

            # 🔥 FALLBACK (organic)
            for res in data.get("organic_results", []):
                text = (res.get("title", "") + " " + res.get("snippet", "")).lower()

                found = re.findall(r"(\d{2,6})\s*kr", text)

                for f in found:
                    val = int(f)
                    if 20 < val < 100000:
                        prices.append(val)

        except Exception as e:
            print("SEARCH ERROR:", e)

    print("ALL PRICES:", prices)

    return prices


# ---------- CLEAN ----------
def clean(prices):

    if not prices:
        return []

    prices.sort()
    median = prices[len(prices)//2]

    cleaned = [p for p in prices if median * 0.3 < p < median * 3]

    print("CLEAN:", cleaned)

    return cleaned


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
        return {
            "description": "-",
            "price": "-",
            "note": "fejl"
        }

    img64 = base64.b64encode(img).decode("utf-8")

    desc = identify(img64)

    if not desc:
        desc = "ukendt objekt"

    queries = build_queries(desc)

    prices = search_prices(queries)

    prices = clean(prices)

    price = calc(prices)

    if price:
        note = "baseret på lignende fund"
        price_text = f"{price} kr"
    else:
        note = "lignende - ingen direkte fund"
        price_text = "ukendt"

    return {
        "description": desc,
        "price": price_text,
        "note": note,
        "data_points": len(prices)
    }