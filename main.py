import os
import requests
import statistics
import time
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERP_API_KEY = os.getenv("SERP_API_KEY")

# 🔥 Designer detection keywords
DESIGNER_KEYWORDS = [
    "kubus",
    "mogens lassen",
    "by lassen",
    "kubus 4",
    "kubus lysestage"
]


# ----------------------------
# 🧠 IMAGE → BESKRIVELSE (stub / din eksisterende)
# ----------------------------
def analyze_image(image_bytes):
    """
    Her bruger du din nuværende GPT / vision.
    Returnér:
    title, condition, extra
    """

    # 🔧 EKSEMPEL (erstat med din rigtige vision call)
    return {
        "title": "adventsstage",
        "condition": "god stand",
        "extra": "sort metal"
    }


# ----------------------------
# 🔍 SERP SEARCH
# ----------------------------
def search_prices(query):
    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "da"
    }

    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
    except Exception:
        return []

    prices = []

    for r in data.get("organic_results", []):
        text = r.get("snippet", "") + " " + r.get("title", "")

        # find tal
        for word in text.split():
            try:
                p = int(word.replace("kr", "").replace(".", "").replace(",", ""))
                if 10 < p < 20000:
                    prices.append(p)
            except:
                pass

    return prices


# ----------------------------
# 🔥 DESIGNER FILTER
# ----------------------------
def filter_designer(prices, title):
    title_lower = title.lower()

    if any(k in title_lower for k in DESIGNER_KEYWORDS):
        # fjern kopier / små modeller
        prices = [p for p in prices if p >= 150]

    return prices


# ----------------------------
# 🧹 GENEREL FILTER
# ----------------------------
def clean_prices(prices):
    # fjern 0 og små junk
    prices = [p for p in prices if p > 20]

    if len(prices) < 4:
        return prices

    prices.sort()

    # trim 15% i hver side
    trim = int(len(prices) * 0.15)
    prices = prices[trim: len(prices) - trim]

    return prices


# ----------------------------
# 📊 BEREGN PRIS RANGE
# ----------------------------
def calculate_price(prices):
    if not prices:
        return None, None

    median = statistics.median(prices)

    low = median * 0.9
    high = median * 1.1

    # rund til nærmeste 5 kr
    low = int(round(low / 5) * 5)
    high = int(round(high / 5) * 5)

    return low, high


# ----------------------------
# 🔁 SERP MED RETRY
# ----------------------------
def get_prices_with_retry(query):
    for attempt in range(2):
        prices = search_prices(query)
        if prices:
            return prices
        time.sleep(0.8)

    return []


# ----------------------------
# 🚀 MAIN ENDPOINT
# ----------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()

    # 🧠 image analyse
    result = analyze_image(image_bytes)

    title = result["title"]
    condition = result["condition"]
    extra = result["extra"]

    query = f"{title} {extra}"

    # 🔍 hent priser
    raw_prices = get_prices_with_retry(query)

    print("RAW PRICES:", raw_prices)

    # 🔥 designer filter
    prices = filter_designer(raw_prices, title)

    print("AFTER DESIGNER FILTER:", prices)

    # 🧹 clean + trim
    prices = clean_prices(prices)

    print("AFTER CLEAN:", prices)

    if not prices:
        return {
            "title": title,
            "condition": condition,
            "extra": extra,
            "price_low": None,
            "price_high": None,
            "count": 0
        }

    low, high = calculate_price(prices)

    return {
        "title": title,
        "condition": condition,
        "extra": extra,
        "price_low": low,
        "price_high": high,
        "count": len(prices)
    }