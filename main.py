import os
import re
import json
import base64
import requests
import statistics

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")


# -----------------------------------
# HELPERS
# -----------------------------------
def first_upper(text):
    if not text:
        return ""

    text = text.strip().lower()

    return text[0].upper() + text[1:]


# -----------------------------------
# OPENAI VISION ANALYSIS
# -----------------------------------
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
                        {
                            "type": "text",
                            "text": """
Identificer objektet på billedet.

Svar KUN gyldig JSON.

Format:
{
  "title": "",
  "designer": "",
  "condition": "",
  "material": ""
}

Regler:
- title = kort præcist navn
- designer = kendt designer hvis muligt ellers ""
- condition = kort vurdering på dansk
- material = materiale/type
- ingen forklaring
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 200
        },
        timeout=20
    )

    try:

        content = response.json()["choices"][0]["message"]["content"]

        # FIX markdown wrappers
        content = content.replace("```json", "")
        content = content.replace("```", "")
        content = content.strip()

        parsed = json.loads(content)

        return {
            "title": parsed.get("title", ""),
            "designer": parsed.get("designer", ""),
            "condition": parsed.get("condition", ""),
            "material": parsed.get("material", "")
        }

    except Exception as e:

        print("OPENAI ERROR:", e)

        return {
            "title": "ukendt",
            "designer": "",
            "condition": "ukendt",
            "material": ""
        }


# -----------------------------------
# SMART SEARCH QUERY
# -----------------------------------
def build_query(data):

    title = data["title"].lower()
    material = data["material"].lower()

    # special smartere søgninger
    if "trækasse" in title:
        return "vintage trækasse gammel ølkasse trækasse brugt pris"

    if "fletstol" in title:
        return "fletstol rattan stol brugt dba"

    if "adventsstage" in title:
        return "kubus lysestage mogens lassen brugt"

    parts = []

    if data["designer"]:
        parts.append(data["designer"])

    parts.append(title)

    if material:
        parts.append(material)

    parts.append("brugt")

    query = " ".join(parts)

    print("QUERY:", query)

    return query


# -----------------------------------
# FETCH PRICES
# -----------------------------------
def get_prices(query):

    try:

        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "hl": "da",
                "gl": "dk",
                "api_key": SERP_API_KEY
            },
            timeout=6
        )

        data = response.json()

        organic = data.get("organic_results", [])

        prices = []

        for result in organic:

            text = (
                result.get("title", "") +
                " " +
                result.get("snippet", "")
            ).lower()

            found = re.findall(r'(\d{2,5})\s?kr', text)

            for p in found:

                try:

                    value = int(p)

                    if value < 50:
                        continue

                    if value > 5000:
                        continue

                    prices.append(value)

                except:
                    pass

        print("RAW:", prices)

        return prices

    except Exception as e:

        print("SERP ERROR:", e)

        return []


# -----------------------------------
# FILTER PRICES
# -----------------------------------
def filter_prices(prices):

    if not prices:
        return []

    # remove duplicates
    prices = sorted(list(set(prices)))

    if len(prices) < 3:
        return prices

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        # fjern vilde outliers
        if p > median * 0.45 and p < median * 2.2:
            filtered.append(p)

    print("FILTERED:", filtered)

    return filtered


# -----------------------------------
# BUILD RANGE
# -----------------------------------
def make_price_range(prices):

    if not prices:
        return None

    median = int(statistics.median(prices))

    low = int(round((median * 0.9) / 5) * 5)
    high = int(round((median * 1.1) / 5) * 5)

    return f"{low} - {high} kr"


# -----------------------------------
# API
# -----------------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()

    # 1 vision
    data = analyze_image(image_bytes)

    print("VISION:", data)

    # 2 build search
    query = build_query(data)

    # 3 fetch prices
    raw_prices = get_prices(query)

    # 4 filter
    filtered = filter_prices(raw_prices)

    # 5 range
    price_range = make_price_range(filtered)

    title = first_upper(data["title"])
    material = data["material"].lower()
    condition = first_upper(data["condition"])

    # ingen fake fallback
    if not price_range:

        return {
            "title": title,
            "extra": material,
            "price": None,
            "condition": condition,
            "count": 0
        }

    return {
        "title": title,
        "extra": material,
        "price": price_range,
        "condition": condition,
        "count": len(filtered)
    }


@app.get("/")
def root():
    return {"status": "ok"}