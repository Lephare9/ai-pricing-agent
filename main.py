import os
import io
import re
import json
import statistics
import requests

from typing import List

from PIL import Image

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from google.cloud import vision
from google.oauth2 import service_account


# =========================================================
# CONFIG
# =========================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not SERPAPI_KEY:
    raise Exception("Missing SERPAPI_KEY")

GOOGLE_CREDS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

if not GOOGLE_CREDS_JSON:
    raise Exception("Missing GOOGLE_APPLICATION_CREDENTIALS_JSON")


# =========================================================
# GOOGLE VISION
# =========================================================

credentials_info = json.loads(GOOGLE_CREDS_JSON)

credentials = service_account.Credentials.from_service_account_info(
    credentials_info
)

vision_client = vision.ImageAnnotatorClient(
    credentials=credentials
)


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

DANISH_WORDS = {
    "chair": "stol",
    "armchair": "lænestol",
    "rattan": "rattan",
    "wicker": "flet",
    "cabinet": "skab",
    "drawer": "kommode",
    "table": "bord",
    "lamp": "lampe",
    "wood": "træ",
    "glass": "glas",
    "sofa": "sofa",
    "shelf": "hylde",
}


def translate_to_danish(text: str) -> str:

    text = text.lower()

    for eng, dk in DANISH_WORDS.items():
        text = text.replace(eng, dk)

    return text


def clean_title(text: str) -> str:

    text = translate_to_danish(text)

    text = re.sub(r"[^a-zA-ZæøåÆØÅ0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_prices(text: str) -> List[int]:

    prices = []

    patterns = [
        r"(\d{2,5})\s?kr",
        r"kr\s?(\d{2,5})",
        r"(\d{2,5})\s?dkk",
    ]

    for pattern in patterns:

        matches = re.findall(pattern, text.lower())

        for match in matches:

            try:

                price = int(match)

                if 50 <= price <= 50000:
                    prices.append(price)

            except:
                pass

    return prices


def filter_prices(prices: List[int]) -> List[int]:

    if not prices:
        return []

    prices = sorted(prices)

    median = statistics.median(prices)

    filtered = []

    for price in prices:

        if price < median * 0.45:
            continue

        if price > median * 2.2:
            continue

        filtered.append(price)

    return filtered


def detect_material(title: str) -> str:

    title = title.lower()

    materials = []

    if "træ" in title:
        materials.append("Træ")

    if "teak" in title:
        materials.append("Teaktræ")

    if "eg" in title:
        materials.append("Eg")

    if "glas" in title:
        materials.append("Glas")

    if "rattan" in title:
        materials.append("Rattan")

    if "flet" in title:
        materials.append("Flet")

    if not materials:
        return "Ukendt materiale"

    return ", ".join(materials)


def search_google_lens(image_base64: str):

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google_lens",
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "url": f"data:image/jpeg;base64,{image_base64}",
    }

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    return response.json()


def collect_visual_titles(data) -> List[str]:

    titles = []

    visual_matches = data.get("visual_matches", [])

    for item in visual_matches[:10]:

        title = item.get("title")

        if title:

            title = clean_title(title)

            if len(title) > 3:
                titles.append(title)

    return titles


def collect_prices(data) -> List[int]:

    prices = []

    visual_matches = data.get("visual_matches", [])

    for item in visual_matches:

        text_blob = json.dumps(item)

        found = extract_prices(text_blob)

        prices.extend(found)

    shopping = data.get("shopping_results", [])

    for item in shopping:

        text_blob = json.dumps(item)

        found = extract_prices(text_blob)

        prices.extend(found)

    return prices


def pick_best_title(titles: List[str]) -> str:

    if not titles:
        return "Ukendt objekt"

    counter = {}

    for title in titles:

        words = title.split()

        for word in words:

            if len(word) < 4:
                continue

            counter[word] = counter.get(word, 0) + 1

    sorted_words = sorted(
        counter.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    top_words = [w[0] for w in sorted_words[:4]]

    final = " ".join(top_words)

    return final.capitalize()


# =========================================================
# ROUTES
# =========================================================

@app.get("/")
async def root():

    return {
        "status": "ok"
    }


@app.post("/analyze")
async def analyze_image(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        pil_image = Image.open(io.BytesIO(image_bytes))

        buffered = io.BytesIO()

        pil_image.save(buffered, format="JPEG")

        image_bytes = buffered.getvalue()

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # =====================================================
        # GOOGLE LENS SEARCH
        # =====================================================

        lens_data = search_google_lens(image_base64)

        # =====================================================
        # VISUAL TITLES
        # =====================================================

        visual_titles = collect_visual_titles(lens_data)

        print("VISUAL TITLES:", visual_titles)

        # =====================================================
        # PRICES
        # =====================================================

        raw_prices = collect_prices(lens_data)

        print("RAW PRICES:", raw_prices)

        filtered_prices = filter_prices(raw_prices)

        print("FILTERED PRICES:", filtered_prices)

        if filtered_prices:

            low_price = min(filtered_prices)
            high_price = max(filtered_prices)

        else:

            low_price = 0
            high_price = 0

        # =====================================================
        # TITLE
        # =====================================================

        title = pick_best_title(visual_titles)

        # =====================================================
        # MATERIAL
        # =====================================================

        material = detect_material(title)

        # =====================================================
        # CONDITION
        # =====================================================

        condition = "Brugt med almindelige brugsspor"

        # =====================================================
        # RESPONSE
        # =====================================================

        return {
            "title": title,
            "material": material,
            "condition": condition,
            "price_low": low_price,
            "price_high": high_price,
            "currency": "DKK",
            "found_prices": len(filtered_prices),
            "visual_matches_found": len(visual_titles),
            "visual_titles": visual_titles[:10],
        }

    except Exception as e:

        print("ANALYZE ERROR:", str(e))

        return {
            "error": str(e)
        }