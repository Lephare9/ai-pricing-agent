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
# DANISH TRANSLATIONS
# =========================================================

DANISH_MAP = {
    "chair": "stol",
    "armchair": "lænestol",
    "table": "bord",
    "cabinet": "skab",
    "drawer": "kommode",
    "lamp": "lampe",
    "sofa": "sofa",
    "shelf": "hylde",
    "wood": "træ",
    "glass": "glas",
    "metal": "metal",
    "plastic": "plast",
    "furniture": "møbel",
    "rattan": "rattan",
    "wicker": "flet",
    "crate": "trækasse",
    "box": "kasse",
    "storage": "opbevaring",
}


STOPWORDS = {
    "wood",
    "brown",
    "black",
    "white",
    "grey",
    "gray",
    "hardwood",
    "display",
    "device",
    "panel",
    "flat",
    "furniture",
    "metal",
    "plastic",
    "silver",
    "iron",
    "modern",
    "design",
    "home",
    "interior",
    "plank",
    "stain",
    "hardtræ",
    "screen",
    "monitor",
}


VALID_DANISH_WORDS = {
    "stol",
    "lænestol",
    "bord",
    "skab",
    "kommode",
    "lampe",
    "hylde",
    "reol",
    "trækasse",
    "vinkasse",
    "trækiste",
    "sofa",
    "skammel",
    "bænk",
    "rattan",
    "flet",
    "træ",
    "glas",
    "metal",
    "plast",
    "teak",
    "teaktræ",
    "eg",
    "opbevaring",
    "kasse",
    "kiste",
}


# =========================================================
# HELPERS
# =========================================================

def clean_text(text: str) -> str:

    if not text:
        return ""

    text = text.lower()

    for eng, dk in DANISH_MAP.items():
        text = text.replace(eng, dk)

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

    if len(prices) < 3:
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

    if "metal" in text:
        found.append("Metal")

    if "plast" in text:
        found.append("Plast")

    if "rattan" in text:
        found.append("Rattan")

    if "flet" in text:
        found.append("Flet")

    if not found:
        return "Ukendt"

    return ", ".join(list(set(found)))


# =========================================================
# GOOGLE VISION
# =========================================================

def vision_detect_labels(image_bytes):

    image = vision.Image(content=image_bytes)

    response = vision_client.label_detection(image=image)

    labels = []

    for label in response.label_annotations[:10]:

        cleaned = clean_text(label.description)

        if cleaned:
            labels.append(cleaned)

    return labels


def vision_web_detection(image_bytes):

    image = vision.Image(content=image_bytes)

    response = vision_client.web_detection(image=image)

    web = response.web_detection

    results = []

    if web.web_entities:

        for entity in web.web_entities[:10]:

            if entity.description:

                cleaned = clean_text(entity.description)

                if not cleaned:
                    continue

                bad_words = [
                    "display",
                    "device",
                    "panel",
                    "flat",
                    "screen",
                    "monitor",
                    "plastic",
                    "silver",
                    "grey",
                    "gray",
                    "brown",
                    "black",
                    "white",
                    "wood",
                    "hardwood",
                ]

                skip = False

                for bad in bad_words:

                    if bad in cleaned:
                        skip = True
                        break

                if not skip:
                    results.append(cleaned)

    return results


# =========================================================
# SERPAPI
# =========================================================

def serpapi_google_lens(image_base64):

    try:

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
            timeout=45,
        )

        print("SERPAPI STATUS:", response.status_code)
        print("SERPAPI RAW:", response.text[:300])

        if response.status_code != 200:
            return {}

        if not response.text.strip():
            return {}

        try:
            return response.json()

        except Exception as e:

            print("SERPAPI JSON ERROR:", str(e))

            return {}

    except Exception as e:

        print("SERPAPI ERROR:", str(e))

        return {}


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


# =========================================================
# TITLE BUILDER
# =========================================================

def build_title(labels, web_entities, visual_titles):

    combined = []

    combined.extend(labels)
    combined.extend(web_entities)
    combined.extend(visual_titles)

    combined = [clean_text(x) for x in combined]

    counts = {}

    for text in combined:

        words = text.split()

        for word in words:

            word = word.strip().lower()

            if len(word) < 3:
                continue

            if word in STOPWORDS:
                continue

            if not re.match(r"^[a-zA-ZæøåÆØÅ]+$", word):
                continue

            counts[word] = counts.get(word, 0) + 1

    if not counts:
        return "Ukendt møbel"

    prioritized = []

    for word, score in counts.items():

        boost = 0

        if word in VALID_DANISH_WORDS:
            boost += 10

        prioritized.append(
            (word, score + boost)
        )

    prioritized = sorted(
        prioritized,
        key=lambda x: x[1],
        reverse=True
    )

    top_words = []

    for word, score in prioritized:

        if word not in top_words:
            top_words.append(word)

        if len(top_words) >= 3:
            break

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

        # =====================================================
        # IMAGE
        # =====================================================

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
        # SERPAPI
        # =====================================================

        lens_data = serpapi_google_lens(image_base64)

        visual_titles = []

        if lens_data:
            visual_titles = get_visual_titles(lens_data)

        print("VISUAL TITLES:", visual_titles)

        raw_prices = []

        if lens_data:
            raw_prices = get_prices(lens_data)

        print("RAW PRICES:", raw_prices)

        filtered_prices = filter_prices(raw_prices)

        print("FILTERED:", filtered_prices)

        # =====================================================
        # PRICE
        # =====================================================

        if filtered_prices:

            low_price = min(filtered_prices)
            high_price = max(filtered_prices)

        else:

            low_price = 0
            high_price = 0

        # =====================================================
        # TITLE
        # =====================================================

        title = build_title(
            labels,
            web_entities,
            visual_titles,
        )

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
        # RESPONSE
        # =====================================================

        return {
            "title": title,
            "material": material,
            "condition": "Brugt med almindelige brugsspor",
            "price_low": low_price,
            "price_high": high_price,
            "currency": "DKK",
            "found_prices": len(filtered_prices),
            "labels": labels,
            "web_entities": web_entities,
            "visual_titles": visual_titles,
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