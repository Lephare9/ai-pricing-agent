from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re

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
SERP_API_KEY = os.getenv("SERP_API_KEY")

print("STARTING APP...")
print("GEMINI KEY:", bool(GEMINI_API_KEY))
print("SERP KEY:", bool(SERP_API_KEY))


# ---------- ROOT ----------
@app.get("/")
def root():
    return {"status": "ok - v15.3"}


# ---------- GEMINI ----------
def call_gemini(image_base64):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {"text": "Identify object + brand if possible. Short answer."},
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
        print("GEMINI RAW:", r.text[:500])

        if r.status_code != 200:
            return None

        data = r.json()

        if "candidates" not in data:
            return None

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        print("GEMINI ERROR:", e)
        return None


# ---------- GOOGLE SEARCH ----------
def google_prices(query):

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

            matches = re.findall(r"(\d{2,5})\s*kr", text)

            for m in matches:
                val = int(m)
                if 20 < val < 50000:
                    prices.append(val)

    except Exception as e:
        print("SEARCH ERROR:", e)

    print("RAW PRICES:", prices[:10])

    return prices


# ---------- FILTER ----------
def filter_prices(prices):

    if not prices:
        return []

    prices = sorted(prices)
    mid = prices[len(prices)//2]

    filtered = [p for p in prices if mid*0.5 < p < mid*2]

    print("FILTERED:", filtered)

    return filtered


# ---------- API ----------
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

    # ---------- AI IDENTIFY ----------
    name = call_gemini(img64)

    if not name:
        name = "ukendt produkt"

    print("IDENTIFIED:", name)

    # ---------- PRICE SEARCH ----------
    prices = google_prices(name)

    if not prices:
        prices = google_prices(name + " brugt")

    prices = filter_prices(prices)

    # ---------- PRICE CALC ----------
    if len(prices) >= 2:
        avg = sum(prices) / len(prices)
        low = int(avg * 0.9)
        high = int(avg * 1.1)
    else:
        low, high = 100, 500

    return {
        "description": name,
        "price_range": f"{low} - {high} kr"
    }