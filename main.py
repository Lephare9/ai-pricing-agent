import os
import io
import re
import json
import base64
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

DANISH_STOPWORDS = {
    "med",
    "og",
    "på",
    "i",
    "af",
    "den",
    "det",
    "til",
    "for",
    "en",
    "et",
    "lille",
    "stor",
    "små",
    "brugt",
    "retro",
    "vintage",
    "teak",
    "teaktræ",
}


def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-zA-ZæøåÆØÅ0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_search_queries(
    web_entities: List[str],
    labels: List[str],
) -> List[str]:

    terms = []

    for item in web_entities:
        item = clean_text(item)

        if len(item) < 3:
            continue

        terms.append(item)

    for item in labels:
        item = clean_text(item)

        if len(item) < 3:
            continue

        terms.append(item)

    final_terms = []

    for item in terms:

        words = [
            w for w in item.split()
            if w not in DANISH_STOPWORDS and len(w) > 2
        ]

        cleaned = " ".join(words)

        if cleaned and cleaned not in final_terms:
            final_terms.append(cleaned)

    queries = []

    if final_terms:
        queries.append(final_terms[0])

    if len(final_terms) >= 2:
        queries.append(final_terms[0] + " " + final_terms[1])

    return queries[:3]


def extract_prices(text: str) -> List[int]:

    prices = []

    patterns = [
        r"(\d{2,5})\s?kr",
        r"kr\s?(\d{2,5})",
        r"(\d{2,5})",
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

    for p in prices:

        if p < median * 0.35:
            continue

        if p > median * 2.5:
            continue

        filtered.append(p)

    return filtered


def search_google_shopping(query: str):

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "gl": "dk",
        "hl": "da",
        "api_key": SERPAPI_KEY,
    }

    response = requests.get(
        url,
        params=params,
        timeout=10,
    )

    return response.json()


def collect_prices(data) -> List[int]:

    prices = []

    organic = data.get("organic_results", [])

    for item in organic:

        text_blob = json.dumps(item)

        found = extract_prices(text_blob)

        prices.extend(found)

    shopping = data.get("shopping_results", [])

    for item in shopping:

        text_blob = json.dumps(item)

        found = extract_prices(text_blob)

        prices.extend(found)

    return prices


def estimate_condition(image_labels: List[str]) -> str:

    labels_text = " ".join(image_labels).lower()

    if "damaged" in labels_text:
        return "Brugt med tydelige brugsspor"

    if "wood" in labels_text:
        return "Brugt med almindelige brugsspor"

    return "Brugt stand"


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

        content = buffered.getvalue()

        vision_image = vision.Image(content=content)

        # =====================================================
        # WEB DETECTION
        # =====================================================

        web_detection = vision_client.web_detection(
            image=vision_image
        ).web_detection

        web_entities = []

        for entity in web_detection.web_entities[:5]:

            if entity.description:
                web_entities.append(entity.description)

        # =====================================================
        # LABELS
        # =====================================================

        label_response = vision_client.label_detection(
            image=vision_image
        )

        labels = []

        for label in label_response.label_annotations[:10]:
            labels.append(label.description)

        print("WEB ENTITIES:", web_entities)
        print("LABELS:", labels)

        # =====================================================
        # SEARCH QUERIES
        # =====================================================

        queries = build_search_queries(
            web_entities,
            labels,
        )

        print("QUERIES:", queries)

        all_prices = []

        for query in queries:

            try:

                result = search_google_shopping(query)

                prices = collect_prices(result)

                all_prices.extend(prices)

            except Exception as e:
                print("SEARCH ERROR:", e)

        print("RAW PRICES:", all_prices)

        filtered_prices = filter_prices(all_prices)

        print("FILTERED:", filtered_prices)

        if filtered_prices:

            low_price = int(min(filtered_prices))
            high_price = int(max(filtered_prices))

        else:

            low_price = 0
            high_price = 0

        # =====================================================
        # TITLE
        # =====================================================

        title = "Ukendt objekt"

        if web_entities:
            title = web_entities[0]

        elif labels:
            title = " ".join(labels[:3])

        title = title.capitalize()

        # =====================================================
        # MATERIAL
        # =====================================================

        material = "Ukendt materiale"

        labels_text = " ".join(labels).lower()

        if "wood" in labels_text:
            material = "Træ"

        if "glass" in labels_text:
            material += ", glas"

        condition = estimate_condition(labels)

        return {
            "title": title,
            "material": material,
            "condition": condition,
            "price_low": low_price,
            "price_high": high_price,
            "currency": "DKK",
            "found_prices": len(filtered_prices),
            "queries_used": queries,
            "web_entities": web_entities,
            "labels": labels,
        }

    except Exception as e:

        print("ANALYZE ERROR:", str(e))

        return {
            "error": str(e)
        }