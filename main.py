import os
import requests
import statistics
import time
import re
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERP_API_KEY = os.getenv("SERP_API_KEY")

DESIGNER_KEYWORDS = [
    "kubus",
    "mogens lassen",
    "by lassen"
]


# ----------------------------
# 🧠 IMAGE ANALYSE (din egen)
# ----------------------------
def analyze_image(image_bytes):
    return {
        "title": "adventsstage",
        "condition": "god stand",
        "extra": "sort metal"
    }


# ----------------------------
# 🔍 PRICE EXTRACTION
# ----------------------------
def extract_prices(text):
    matches = re.findall(r"\d+", text)
    return [int(m) for m in matches]


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
    except:
        return []

    prices = []

    for r in data.get("organic_results", []):
        text = r.get("snippet", "") + " " + r.get("title", "")
        prices += extract_prices(text)

    return prices


# ----------------------------
# 🔥 DESIGNER FILTER (INGEN fallback)
# ----------------------------
def filter_designer(prices, title):
    title_lower = title.lower()

    if any(k in title_lower for k in DESIGNER_KEYWORDS):
        return [p for p in prices if p >= 150]

    return prices


# ----------------------------
# 🧹 CLEAN (ingen fallback)
# ----------------------------
def clean_prices(prices):
    prices = [p for p in prices if 20 < p < 10000]

    if len(prices) < 3:
        return prices

    prices.sort()

    trim = int(len(prices) * 0.1)
    return prices[trim: len(prices) - trim]


# ----------------------------
# 📊 PRICE RANGE
# ----------------------------
def calculate_price(prices):
    if not prices:
        return None, None

    median = statistics.median(prices)

    low = int(round((median * 0.9) / 5) * 5)
    high = int(round((median * 1.1) / 5) * 5)

    return low, high


# ----------------------------
# 🔁 RETRY (hurtig)
# ----------------------------
def get_prices_with_retry(query):
    for _ in range(2):
        prices = search_prices(query)
        if prices:
            return prices
        time.sleep(0.8)

    return []


# ----------------------------
# 🚀 ENDPOINT
# ----------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    result = analyze_image(image_bytes)

    title = result["title"]
    condition = result["condition"]
    extra = result["extra"]

    query = f"{title} {extra}"

    raw_prices = get_prices_with_retry(query)
    print("RAW:", raw_prices)

    if not raw_prices:
        return {
            "title": title,
            "condition": condition,
            "extra": extra,
            "price_low": None,
            "price_high": None,
            "count": 0
        }

    prices = filter_designer(raw_prices, title)
    prices = clean_prices(prices)

    print("FINAL:", prices)

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