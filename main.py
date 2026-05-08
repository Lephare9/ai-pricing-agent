from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
import io
import re
import json
import statistics
import requests

from PIL import Image
from google import genai

# =========================================================
# CONFIG
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not GEMINI_API_KEY:
    raise Exception("Missing GEMINI_API_KEY")

if not SERPAPI_KEY:
    raise Exception("Missing SERPAPI_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================================
# FASTAPI
# =========================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# HELPERS
# =========================================================

STOPWORDS = {
    "flot",
    "smuk",
    "fin",
    "dejlig",
    "moderne",
    "klassisk",
    "retro",
    "vintage",
    "gammel",
    "unik",
    "sjælden",
    "brugt",
    "stand",
    "god",
    "meget",
    "lille",
    "stor",
}


SEARCH_SITES = [
    "dba.dk",
    "facebook.com",
    "etsy.com",
    "ebay.com",
    "ebay.de",
    "trendsales.dk",
]


def title_case(text: str) -> str:
    if not text:
        return ""

    return text[:1].upper() + text[1:]


def clean_title(title: str) -> str:
    if not title:
        return "Ukendt objekt"

    title = title.strip()
    title = re.sub(r"\s+", " ", title)

    return title_case(title)


def clean_material(material: str) -> str:
    if not material:
        return ""

    return title_case(material.strip())


def clean_condition(condition: str) -> str:
    if not condition:
        return ""

    return title_case(condition.strip())


def simplify_query(text: str) -> str:
    words = re.findall(r"\w+", text.lower())

    cleaned = []

    for w in words:
        if len(w) < 3:
            continue

        if w in STOPWORDS:
            continue

        cleaned.append(w)

    return " ".join(cleaned[:6])


def extract_prices(text: str):
    matches = re.findall(r"(\d{2,6})\s*(?:kr|dkk)?", text.lower())

    prices = []

    for m in matches:
        try:
            p = int(m)

            if 20 <= p <= 100000:
                prices.append(p)

        except:
            pass

    return prices


def remove_outliers(prices):
    if len(prices) < 3:
        return prices

    median = statistics.median(prices)

    filtered = []

    for p in prices:
        if median * 0.5 <= p <= median * 1.8:
            filtered.append(p)

    return filtered


def round_to_5(value):
    return int(round(value / 5) * 5)


def calculate_price_range(prices):
    if not prices:
        return None

    prices = remove_outliers(prices)

    if not prices:
        return None

    median_price = statistics.median(prices)

    low = median_price * 0.9
    high = median_price * 1.1

    low = round_to_5(low)
    high = round_to_5(high)

    if low == high:
        return f"{low} kr"

    return f"{low} – {high} kr"


def serpapi_search(query: str):
    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "num": 10,
    }

    response = requests.get(
        url,
        params=params,
        timeout=20,
    )

    data = response.json()

    return data.get("organic_results", [])


def gather_prices(query: str):
    all_prices = []

    for site in SEARCH_SITES:
        try:
            full_query = f"{query} site:{site}"

            results = serpapi_search(full_query)

            for result in results:
                text = ""

                if "title" in result:
                    text += " " + result["title"]

                if "snippet" in result:
                    text += " " + result["snippet"]

                prices = extract_prices(text)

                all_prices.extend(prices)

        except Exception as e:
            print("SEARCH ERROR:", e)

    return all_prices


# =========================================================
# ANALYZE
# =========================================================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()

        image = Image.open(io.BytesIO(image_bytes))

        prompt = """
Du analyserer et brugt objekt.

Returnér KUN valid JSON.

Format:

{
  "title": "",
  "material": "",
  "condition": "",
  "designer": "",
  "search_terms": []
}

Regler:
- title skal være realistisk og konkret
- ingen fantasinavne
- ingen pris
- designer kun hvis meget sikker
- material skal være kort
- condition skal være realistisk
- search_terms skal være gode søgninger til brugtmarked
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                prompt,
                image,
            ]
        )

        raw = response.text.strip()

        raw = raw.replace("```json", "")
        raw = raw.replace("```", "")

        vision = json.loads(raw)

        title = clean_title(
            vision.get("title", "Ukendt objekt")
        )

        material = clean_material(
            vision.get("material", "")
        )

        condition = clean_condition(
            vision.get("condition", "")
        )

        search_terms = vision.get("search_terms", [])

        queries = []

        queries.append(
            simplify_query(
                f"{title} {material}"
            )
        )

        for s in search_terms:
            queries.append(
                simplify_query(s)
            )

        queries = list(dict.fromkeys(queries))

        all_prices = []

        for q in queries[:5]:
            prices = gather_prices(q)

            all_prices.extend(prices)

        filtered_prices = remove_outliers(all_prices)

        price_text = calculate_price_range(filtered_prices)

        if not price_text:
            price_text = "Ukendt pris"

        print("VISION:", vision)
        print("QUERIES:", queries)
        print("RAW:", all_prices)
        print("FILTERED:", filtered_prices)

        return JSONResponse({
            "title": title,
            "material": material,
            "condition": condition,
            "price": price_text,
            "found_prices": len(filtered_prices),
        })

    except Exception as e:
        print("ANALYZE ERROR:", str(e))

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "status": "ok"
    }