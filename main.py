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
    return {"status": "ok - v15.4"}


# ---------- CLEAN TEXT ----------
def clean_text(text):
    text = text.split(".")[0]  # kun første sætning
    text = re.sub(r"used for.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"containing.*", "", text, flags=re.IGNORECASE)
    return text.strip()


# ---------- GEMINI ----------
def call_gemini(img64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": "Svar på dansk. Hvad er dette objekt? Kort navn."},
                {"inline_data": {"mime_type": "image/jpeg", "data": img64}}
            ]
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=15)

        print("GEMINI:", r.status_code)

        if r.status_code != 200:
            return None

        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]

        return clean_text(text)

    except Exception as e:
        print("GEMINI ERROR:", e)
        return None


# ---------- SEARCH ----------
def search_prices(query):

    if not SERP_API_KEY:
        return []

    url = "https://serpapi.com/search"

    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "da",
        "gl": "dk"
    }

    prices = []

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        for res in data.get("organic_results", []):
            text = (res.get("title", "") + " " + res.get("snippet", "")).lower()

            found = re.findall(r"(\d{2,6})\s*kr", text)

            for f in found:
                val = int(f)
                if 10 < val < 100000:
                    prices.append(val)

    except Exception as e:
        print("SEARCH ERROR:", e)

    print("ALL PRICES:", prices)

    return prices


# ---------- FINAL PRICE ----------
def get_price(prices):

    if not prices:
        return "ingen pris fundet"

    prices.sort()

    median = prices[len(prices)//2]

    return f"{median} kr"


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()

    if not img:
        return {"description": "ingen fil", "price": "ingen pris"}

    img64 = base64.b64encode(img).decode("utf-8")

    name = call_gemini(img64)

    if not name:
        name = "ukendt produkt"

    print("NAME:", name)

    prices = search_prices(name)
    prices += search_prices(name + " Danmark")

    price = get_price(prices)

    return {
        "description": name,
        "price": price,
        "raw_prices": prices[:10]
    }