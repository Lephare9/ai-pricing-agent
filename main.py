import os
import re
import base64
import requests
import statistics
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")

# -------------------------
# IMAGE ANALYSIS (REAL AI)
# -------------------------
def analyze_image(image_bytes):
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": """
Identificer objektet meget præcist.

Svar KUN JSON:
{
  "title": "",
  "designer": "",
  "condition": "",
  "material": ""
}

Regler:
- title: specifikt navn (fx "kubus lysestage", "fletstol", "trækrukke")
- designer: hvis kendt (fx "Mogens Lassen"), ellers ""
- condition: kort (fx "god stand", "slidt", "velholdt")
- material: fx "rattan", "sort metal", "eg"
"""},

                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        }
    )

    try:
        content = response.json()["choices"][0]["message"]["content"]
        return eval(content)
    except:
        return {
            "title": "Ukendt",
            "designer": "",
            "condition": "Ukendt",
            "material": ""
        }


# -------------------------
# BUILD SEARCH QUERY
# -------------------------
def build_query(data):
    parts = []

    if data["designer"]:
        parts.append(data["designer"])

    parts.append(data["title"])

    if data["material"]:
        parts.append(data["material"])

    # vigtig: brugt + dansk
    parts.append("brugt")

    return " ".join(parts)


# -------------------------
# GET PRICES (SERP)
# -------------------------
def get_prices(query):
    url = "https://serpapi.com/search.json"

    params = {
        "q": query,
        "engine": "google",
        "api_key": SERP_API_KEY,
        "hl": "da",
        "gl": "dk"
    }

    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
    except:
        return []

    prices = []

    results = data.get("organic_results", [])

    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()

        matches = re.findall(r'(\d{2,5})\s?kr', text)

        for m in matches:
            val = int(m)

            # hård filtrering
            if val < 50:
                continue
            if val > 5000:
                continue

            prices.append(val)

    return prices


# -------------------------
# SMART FILTER
# -------------------------
def filter_prices(prices):
    if not prices or len(prices) < 3:
        return []

    prices.sort()

    # fjern yderste 20%
    cut = int(len(prices) * 0.2)
    core = prices[cut:-cut] if len(prices) > 5 else prices

    if len(core) < 3:
        return []

    # median-baseret filter
    median = statistics.median(core)

    filtered = [p for p in core if 0.5 * median < p < 1.8 * median]

    return filtered


# -------------------------
# PRICE RANGE
# -------------------------
def make_range(prices):
    if not prices:
        return None

    median = int(statistics.median(prices))

    low = int(round(median * 0.9 / 5) * 5)
    high = int(round(median * 1.1 / 5) * 5)

    return low, high


# -------------------------
# FORMAT
# -------------------------
def capitalize_first(text):
    if not text:
        return ""
    return text[0].upper() + text[1:]


# -------------------------
# API
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()

    data = analyze_image(image_bytes)

    query = build_query(data)

    raw_prices = get_prices(query)

    print("RAW:", raw_prices)

    filtered = filter_prices(raw_prices)

    print("FILTERED:", filtered)

    price_range = make_range(filtered)

    if not price_range:
        return {
            "title": capitalize_first(data["title"]),
            "price": None,
            "condition": capitalize_first(data["condition"]),
            "extra": capitalize_first(data["material"]),
            "count": 0
        }

    low, high = price_range

    return {
        "title": capitalize_first(data["title"]),
        "price": f"{low} - {high} kr",
        "condition": capitalize_first(data["condition"]),
        "extra": capitalize_first(data["material"]),
        "count": len(filtered)
    }


@app.get("/")
def root():
    return {"status": "ok"}