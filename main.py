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
    return {"status": "ok - v16"}


# ---------- GEMINI ----------
def identify(img64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """Svar på dansk.
Hvad er objektet? (kort navn, max 5 ord)
Ingen forklaring.
Eksempel: "teak spisebordsstol" """
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

        print("AI:", txt)

        return txt

    except Exception as e:
        print("AI ERROR:", e)
        return None


# ---------- MULTI SEARCH ----------
def search_all(name):

    queries = [
        f"{name} dba",
        f"{name} til salg",
        f"{name} pris",
        f"{name} brugt",
        f"{name} danmark"
    ]

    all_prices = []

    for q in queries:

        print("SEARCH:", q)

        params = {
            "q": q + " site:dba.dk",
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
                        all_prices.append(val)

        except Exception as e:
            print("SEARCH ERROR:", e)

    print("ALL:", all_prices)

    return all_prices


# ---------- FILTER ----------
def clean_prices(prices):

    if not prices:
        return []

    prices.sort()

    # fjern ekstreme outliers
    median = prices[len(prices)//2]

    cleaned = [p for p in prices if median * 0.3 < p < median * 3]

    print("CLEAN:", cleaned)

    return cleaned


# ---------- PRICE ----------
def calculate(prices):

    if not prices:
        return None

    prices.sort()
    median = prices[len(prices)//2]

    return median


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()

    if not img:
        return {"description": "ingen fil", "price": "-", "note": "fejl"}

    img64 = base64.b64encode(img).decode("utf-8")

    name = identify(img64)

    if not name or len(name) < 3:
        name = "ukendt objekt"

    prices = search_all(name)

    prices = clean_prices(prices)

    price = calculate(prices)

    if price:
        note = "fundet via lignende"
        price_text = f"{price} kr"
    else:
        note = "lignende - ingen direkte fund"
        price_text = "ukendt"

    return {
        "description": name,
        "price": price_text,
        "note": note,
        "data_points": len(prices)
    }