from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
import io
import re
import json
import statistics
import traceback
import requests

from concurrent.futures import ThreadPoolExecutor

from PIL import Image
import google.generativeai as genai

# =========================================================
# CONFIG
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not GEMINI_API_KEY:
    raise Exception("Missing GEMINI_API_KEY")

if not SERPAPI_KEY:
    raise Exception("Missing SERPAPI_KEY")

genai.configure(api_key=GEMINI_API_KEY)

vision_model = genai.GenerativeModel("gemini-2.5-flash")

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
# FAST MODE CONFIG
# =========================================================

SEARCH_SITES = [
    "dba.dk",
    "facebook.com",
]

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

# simpel RAM cache
SEARCH_CACHE = {}

# =========================================================
# HELPERS
# =========================================================

def title_case(text: str):
    if not text:
        return ""

    return text[:1].upper() + text[1:]


def clean_title(title: str):
    if not title:
        return "Ukendt objekt"

    title = re.sub(r"\s+", " ", title.strip())

    return title_case(title)


def clean_material(material: str):
    if not material:
        return ""

    return title_case(material.strip())


def clean_condition(condition: str):
    if not condition:
        return ""

    return title_case(condition.strip())


def simplify_query(text: str):
    words = re.findall(r"\w+", text.lower())

    cleaned = []

    for w in words:
        if len(w) < 3:
            continue

        if w in STOPWORDS:
            continue

        cleaned.append(w)

    return " ".join(cleaned[:5])


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
        if median * 0.6 <= p <= median * 1.5:
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

    low = round_to_5(median_price * 0.9)
    high = round_to_5(median_price * 1.1)

    if low == high:
        return f"{low} kr"

    return f"{low} – {high} kr"


# =========================================================
# SEARCH
# =========================================================

def serpapi_search(query: str):
    cache_key = query.lower()

    if cache_key in SEARCH_CACHE:
        return SEARCH_CACHE[cache_key]

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "num": 6,
    }

    response = requests.get(
        url,
        params=params,
        timeout=10,
    )

    data = response.json()

    results = data.get("organic_results", [])

    SEARCH_CACHE[cache_key] = results

    return results


def search_site(query, site):
    try:
        full_query = f"{query} site:{site}"

        results = serpapi_search(full_query)

        prices = []

        for result in results:
            text = ""

            if "title" in result:
                text += " " + result["title"]

            if "snippet" in result:
                text += " " + result["snippet"]

            found = extract_prices(text)

            prices.extend(found)

        return prices

    except Exception as e:
        print("SEARCH ERROR:", e)
        return []


def gather_prices_parallel(query):
    all_prices = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []

        for site in SEARCH_SITES:
            futures.append(
                executor.submit(search_site, query, site)
            )

        for future in futures:
            try:
                prices = future.result()
                all_prices.extend(prices)

            except:
                pass

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

REGLER:
- realistisk titel
- ingen fantasi
- ingen pris
- kort materiale
- realistisk stand
- designer kun hvis meget sikker
- søgetermer korte og konkrete
"""

        response = vision_model.generate_content(
            [
                prompt,
                image
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

        designer = vision.get("designer", "").strip()

        search_terms = vision.get("search_terms", [])

        # =====================================================
        # FAST MODE QUERIES
        # =====================================================

        queries = []

        main_query = simplify_query(
            f"{title} {material}"
        )

        queries.append(main_query)

        if designer:
            designer_query = simplify_query(
                f"{designer} {title}"
            )

            if designer_query not in queries:
                queries.append(designer_query)

        for s in search_terms[:1]:
            q = simplify_query(s)

            if q not in queries:
                queries.append(q)

        # max 2 queries
        queries = queries[:2]

        print("QUERIES:", queries)

        # =====================================================
        # SEARCH
        # =====================================================

        all_prices = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []

            for q in queries:
                futures.append(
                    executor.submit(
                        gather_prices_parallel,
                        q
                    )
                )

            for future in futures:
                try:
                    prices = future.result()
                    all_prices.extend(prices)

                except:
                    pass

        filtered_prices = remove_outliers(all_prices)

        price_text = calculate_price_range(filtered_prices)

        if not price_text:
            price_text = "Ukendt pris"

        print("TITLE:", title)
        print("RAW PRICES:", all_prices)
        print("FILTERED:", filtered_prices)
        print("FINAL:", price_text)

        return JSONResponse({
            "title": title,
            "material": material,
            "condition": condition,
            "price": price_text,
            "found_prices": len(filtered_prices),
        })

    except Exception as e:
        print("ANALYZE ERROR:")
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


@app.get("/")
def root():
    return {
        "status": "ok"
    }