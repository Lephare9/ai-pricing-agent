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

DANISH_MAP = {
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
    "furniture": "møbel",
}


def translate_to_danish(text: str) -> str:

    text = text.lower()

    for eng, dk in DANISH_MAP.items():
        text = text.replace(eng, dk)

    return text


def clean_text(text: str) -> str:

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

                value = int(match)

                if 75 <= value <= 50000:
                    prices.append(value)

            except:
                pass

    return prices


def filter_prices(prices: List[int]) -> List[int]:

    if len(prices) < 2:
        return prices

    prices = sorted(prices)

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        if p < median * 0.45:
            continue

        if p > median * 2.5:
            continue

        filtered.append(p)

    return filtered


def detect_material(text: str) -> str:

    text = text.lower()

    found = []

    if "teak" in text:
        found.append("Teaktræ")

    if "eg" in text:
        found.append("Eg")

    if "træ" in text:
        found.append("Træ")

    if "glas" in text:
        found.append("Glas")

    if "rattan" in text:
        found.append("Rattan")

    if "flet" in text:
        found.append("Flet")

    if not found:
        return "Ukendt materiale"

    return ", ".join(list(set(found)))


def vision_detect_labels(image_bytes):

    image = vision.Image(content=image_bytes)

    response = vision_client.label_detection(image=image)

    labels = []

    for label in response.label_annotations[:8]:

        labels.append(clean_text(label.description))

    return labels


def vision_web_detection(image_bytes):

    image = vision.Image(content=image_bytes)

    response = vision_client.web_detection(image=image)

    web = response.web_detection

    results = []

    if web.web_entities:

        for entity in web.web_entities[:10]:

            if entity.description:

                results.append(clean_text(entity.description))

    return results


def serpapi_google_lens(image_base64):

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
        timeout=40,
    )

    return response.json()


def get_visual_titles(data):

    titles = []

    visual_matches = data.get("visual_matches", [])

    for item in visual_matches[:12]:

        title = item.get("title")

        if not title:
            continue

        title = clean_text(title)

        if len(title) < 4:
            continue

        titles.append(title)

    return titles


def get_prices(data):

    prices = []

    visual_matches = data.get("visual_matches", [])

    for item in visual_matches:

        blob = json.dumps(item)

        found = extract_prices(blob)

        prices.extend(found)

    shopping_results = data.get("shopping_results", [])

    for item in shopping_results:

        blob = json.dumps(item)

        found = extract_prices(blob)

        prices.extend(found)

    return prices


def build_title(
    labels,
    web_entities,
    visual_titles,
):

    combined = []

    combined.extend(labels)
    combined.extend(web_entities)
    combined.extend(visual_titles)

    combined = [x for x in combined if len(x) > 2]

    if not combined:
        return "Ukendt møbel"

    counts = {}

    for text in combined:

        words = text.split()

        for word in words:

            if len(word) < 4:
                continue

            counts[word] = counts.get(word, 0) + 1

    sorted_words = sorted(
        counts.items(),
        key=lambda x: x[1],
        reverse=True
    )

    top_words = [x[0] for x in sorted_words[:4]]

    final_title = " ".join(top_words)

    return final_title.capitalize()


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

        pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        buffer = io.BytesIO()

        pil.save(
            buffer,
            format="JPEG",
            quality=88
        )

        image_bytes = buffer.getvalue()

        image_base64 = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        # =====================================================
        # GOOGLE VISION
        # =====================================================

        labels = vision_detect_labels(image_bytes)

        print("LABELS:", labels)

        web_entities = vision_web_detection(image_bytes)

        print("WEB ENTITIES:", web_entities)

        # =====================================================
        # SERPAPI LENS
        # =====================================================

        lens_data = serpapi_google_lens(image_base64)

        visual_titles = get_visual_titles(lens_data)

        print("VISUAL MATCHES:", visual_titles)

        # =====================================================
        # TITLE
        # =====================================================

        title = build_title(
            labels,
            web_entities,
            visual_titles,
        )

        # =====================================================
        # PRICES
        # =====================================================

        raw_prices = get_prices(lens_data)

        print("RAW PRICES:", raw_prices)

        filtered_prices = filter_prices(raw_prices)

        print("FILTERED:", filtered_prices)

        if filtered_prices:

            low_price = min(filtered_prices)
            high_price = max(filtered_prices)

        else:

            low_price = 0
            high_price = 0

        # =====================================================
        # MATERIAL
        # =====================================================

        combined_text = (
            " ".join(labels)
            + " "
            + " ".join(web_entities)
            + " "
            + " ".join(visual_titles)
        )

        material = detect_material(combined_text)

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
            "labels": labels,
            "web_entities": web_entities,
            "visual_titles": visual_titles[:10],
        }

    except Exception as e:

        print("ANALYZE ERROR:", str(e))

        return {
            "title": "Ukendt",
            "material": "Ukendt",
            "condition": "Ukendt",
            "price_low": 0,
            "price_high": 0,
            "currency": "DKK",
            "found_prices": 0,
            "error": str(e),
        }