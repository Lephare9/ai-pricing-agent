import os
import re
import base64
import statistics
import requests

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from openai import OpenAI

# ---------------------------------------------------
# APP
# ---------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# KEYS
# ---------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def normalize_text(text):

    if not text:
        return ""

    text = text.strip()

    if len(text) == 0:
        return ""

    return text[0].upper() + text[1:].lower()


def normalize_title(text):

    if not text:
        return "Ukendt"

    words = text.strip().split()

    fixed = []

    for i, w in enumerate(words):

        if i == 0:
            fixed.append(w.capitalize())
        else:
            fixed.append(w.lower())

    return " ".join(fixed)


def build_price_range(price):

    low = round((price * 0.9) / 5) * 5
    high = round((price * 1.1) / 5) * 5

    return f"{low} – {high} kr"


# ---------------------------------------------------
# OPENAI VISION
# ---------------------------------------------------

async def analyze_image(image_bytes):

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
Analyser objektet på billedet.

Svar KUN som JSON.

Format:

{
  "title":"",
  "material":"",
  "condition":"",
  "designer":""
}

Regler:
- kort titel
- materiale
- kort stand
- designer kun hvis meget sikker
- ingen forklaring
"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_bytes}"
                        }
                    }
                ]
            }
        ],
        max_tokens=200
    )

    content = response.choices[0].message.content

    try:

        import json

        return json.loads(content)

    except:

        return {
            "title": "Ukendt",
            "material": "",
            "condition": "Ukendt stand",
            "designer": ""
        }


# ---------------------------------------------------
# SEARCH
# ---------------------------------------------------

def search_prices(query):

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk"
    }

    for attempt in range(2):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=4
            )

            data = response.json()

            organic = data.get("organic_results", [])

            text_parts = []

            for r in organic:

                title = r.get("title", "")
                snippet = r.get("snippet", "")

                text_parts.append(title)
                text_parts.append(snippet)

            return " ".join(text_parts)

        except Exception as e:

            print(f"SERP attempt {attempt+1} failed:", e)

            continue

    return ""


# ---------------------------------------------------
# PRICE EXTRACTION
# ---------------------------------------------------

def extract_prices(text):

    matches = re.findall(
        r'(\d{2,5})\s?(?:kr|,-)?',
        text,
        re.IGNORECASE
    )

    prices = []

    for m in matches:

        try:

            p = int(m)

            # fjern støj
            if p < 25:
                continue

            if p > 50000:
                continue

            prices.append(p)

        except:
            pass

    print("RAW:", prices)

    return prices


# ---------------------------------------------------
# FILTER
# ---------------------------------------------------

def filter_prices(prices):

    if len(prices) == 0:
        return []

    prices = sorted(prices)

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        # behold realistiske værdier
        if p >= median * 0.35 and p <= median * 2.8:
            filtered.append(p)

    # fallback hvis filter blev for aggressivt
    if len(filtered) < 3:
        filtered = prices

    print("FILTERED:", filtered)

    return filtered


# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
def root():

    return {
        "status": "ok"
    }


# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image = await file.read()

    image_b64 = base64.b64encode(image).decode()

    vision = await analyze_image(image_b64)

    print("VISION:", vision)

    title = normalize_title(
        vision.get("title", "Ukendt")
    )

    material = normalize_text(
        vision.get("material", "")
    )

    condition = normalize_text(
        vision.get("condition", "Ukendt stand")
    )

    designer = normalize_text(
        vision.get("designer", "")
    )

    # ---------------------------------------------------
    # SEARCH QUERY
    # ---------------------------------------------------

    query_parts = []

    if designer:
        query_parts.append(designer)

    if title:
        query_parts.append(title)

    if material:
        query_parts.append(material)

    query_parts.append("brugt")

    query = " ".join(query_parts)

    print("QUERY:", query)

    # ---------------------------------------------------
    # SEARCH
    # ---------------------------------------------------

    raw_text = search_prices(query)

    prices = extract_prices(raw_text)

    filtered = filter_prices(prices)

    # ---------------------------------------------------
    # RESULT
    # ---------------------------------------------------

    if len(filtered) == 0:

        return {
            "title": title,
            "material": material,
            "condition": condition,
            "designer": designer,
            "price_range": "Ukendt pris",
            "found_prices": 0
        }

    avg_price = int(statistics.mean(filtered))

    price_range = build_price_range(avg_price)

    return {
        "title": title,
        "material": material,
        "condition": condition,
        "designer": designer,
        "price_range": price_range,
        "found_prices": len(filtered)
    }