from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from PIL import Image

from serpapi import GoogleSearch
from google.cloud import vision
from google.oauth2 import service_account

import io
import os
import re
import json
import base64
import statistics
import requests


# ==========================================
# FASTAPI
# ==========================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# ENV
# ==========================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
IMGBB_KEY = os.getenv("IMGBB_KEY")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")


# ==========================================
# GOOGLE VISION AUTH
# ==========================================

vision_client = None

try:

    if GOOGLE_CREDS_JSON:

        creds_dict = json.loads(GOOGLE_CREDS_JSON)

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict
        )

        vision_client = vision.ImageAnnotatorClient(
            credentials=credentials
        )

        print("GOOGLE VISION READY")

except Exception as e:

    print("VISION INIT ERROR:", str(e))


# ==========================================
# STOPWORDS
# ==========================================

STOPWORDS = [
    "amazon",
    "ebay",
    "etsy",
    "chair",
    "table",
    "wood",
    "plastic",
    "display",
    "screen",
    "device",
    "monitor",
    "furniture",
    "metal",
    "black",
    "white",
    "grey",
    "gray",
    "brown",
    "interior",
    "design",
]


# ==========================================
# CLEAN TEXT
# ==========================================

def clean_text(text):

    text = text.lower()

    for word in STOPWORDS:
        text = text.replace(word, "")

    text = re.sub(r"[^a-zæøå0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ==========================================
# EXTRACT PRICES
# ==========================================

def extract_prices(text):

    prices = []

    matches = re.findall(
        r'(\d{2,5})\s?(kr|dkk)?',
        text.lower()
    )

    for match in matches:

        try:

            price = int(match[0])

            if 40 <= price <= 50000:
                prices.append(price)

        except:
            pass

    return prices


# ==========================================
# FILTER PRICES
# ==========================================

def filter_prices(prices):

    if not prices:
        return []

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        if median * 0.35 <= p <= median * 2.5:
            filtered.append(p)

    return filtered


# ==========================================
# PRICE RANGE
# ==========================================

def build_price_range(prices):

    if not prices:
        return "Ukendt pris"

    prices = sorted(prices)

    if len(prices) == 1:
        return f"{prices[0]} kr"

    low = int(statistics.quantiles(prices, n=4)[0])
    high = int(statistics.quantiles(prices, n=4)[2])

    if high < low:
        high = max(prices)

    return f"{low} – {high} kr"


# ==========================================
# GOOGLE VISION ANALYSE
# ==========================================

def analyze_with_vision(image_bytes):

    if not vision_client:
        return {
            "title": "Ukendt møbel",
            "labels": [],
            "entities": [],
        }

    image = vision.Image(content=image_bytes)

    # ---------------------------
    # LABELS
    # ---------------------------

    labels_response = vision_client.label_detection(image=image)

    labels = []

    for label in labels_response.label_annotations:

        txt = clean_text(label.description)

        if txt and txt not in labels:
            labels.append(txt)

    print("LABELS:", labels)

    # ---------------------------
    # WEB DETECTION
    # ---------------------------

    web_response = vision_client.web_detection(image=image)

    web_entities = []

    if web_response.web_detection.web_entities:

        for entity in web_response.web_detection.web_entities:

            if entity.description:

                txt = clean_text(entity.description)

                if len(txt) > 2:
                    web_entities.append(txt)

    print("WEB ENTITIES:", web_entities)

    # ---------------------------
    # TITLE
    # ---------------------------

    title = "Ukendt møbel"

    if web_entities:
        title = web_entities[0]

    elif labels:
        title = " ".join(labels[:3])

    return {
        "title": title,
        "labels": labels,
        "entities": web_entities,
    }


# ==========================================
# UPLOAD IMAGE
# ==========================================

def upload_to_imgbb(image_bytes):

    if not IMGBB_KEY:
        return None

    try:

        encoded = base64.b64encode(image_bytes)

        response = requests.post(
            f"https://api.imgbb.com/1/upload?key={IMGBB_KEY}",
            files={
                "image": encoded
            },
            timeout=30
        )

        data = response.json()

        return data["data"]["url"]

    except Exception as e:

        print("IMGBB ERROR:", str(e))

        return None


# ==========================================
# GOOGLE LENS
# ==========================================

def google_lens_search(image_url):

    params = {
        "engine": "google_lens",
        "url": image_url,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
    }

    search = GoogleSearch(params)

    return search.get_dict()


# ==========================================
# COLLECT PRICES
# ==========================================

def collect_prices(results):

    prices = []

    visual_matches = results.get("visual_matches", [])
    related_content = results.get("related_content", [])
    shopping_results = results.get("shopping_results", [])

    # ---------------------------------
    # VISUAL MATCHES
    # ---------------------------------

    for item in visual_matches[:20]:

        text = ""

        if item.get("title"):
            text += " " + item["title"]

        if item.get("source"):
            text += " " + item["source"]

        if item.get("price"):
            text += " " + str(item["price"])

        found = extract_prices(text)

        prices.extend(found)

    # ---------------------------------
    # RELATED CONTENT
    # ---------------------------------

    for item in related_content[:20]:

        text = ""

        if item.get("title"):
            text += " " + item["title"]

        if item.get("price"):
            text += " " + str(item["price"])

        found = extract_prices(text)

        prices.extend(found)

    # ---------------------------------
    # SHOPPING RESULTS
    # ---------------------------------

    for item in shopping_results[:20]:

        text = ""

        if item.get("title"):
            text += " " + item["title"]

        if item.get("price"):
            text += " " + str(item["price"])

        found = extract_prices(text)

        prices.extend(found)

    print("RAW PRICES:", prices)

    filtered = filter_prices(prices)

    print("FILTERED:", filtered)

    return filtered


# ==========================================
# ANALYZE
# ==========================================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        contents = await file.read()

        # ---------------------------
        # RESIZE IMAGE
        # ---------------------------

        img = Image.open(io.BytesIO(contents))

        img.thumbnail((1200, 1200))

        buffer = io.BytesIO()

        img.save(
            buffer,
            format="JPEG",
            quality=85
        )

        image_bytes = buffer.getvalue()

        # ---------------------------
        # GOOGLE VISION
        # ---------------------------

        vision_data = analyze_with_vision(image_bytes)

        # ---------------------------
        # UPLOAD IMAGE
        # ---------------------------

        image_url = upload_to_imgbb(image_bytes)

        if not image_url:

            return {
                "title": "Fejl",
                "material": "Ukendt",
                "condition": "Ukendt",
                "price": "Kunne ikke hente pris",
                "found_prices": 0,
            }

        print("IMAGE URL:", image_url)

        # ---------------------------
        # GOOGLE LENS
        # ---------------------------

        lens_results = google_lens_search(image_url)

        prices = collect_prices(lens_results)

        # ---------------------------
        # RESULT
        # ---------------------------

        if prices:

            return {
                "title": vision_data["title"].title(),
                "material": "Brugt møbel",
                "condition": "Brugt med almindelige brugsspor",
                "price": build_price_range(prices),
                "found_prices": len(prices),
            }

        return {
            "title": vision_data["title"].title(),
            "material": "Brugt møbel",
            "condition": "Brugt med almindelige brugsspor",
            "price": "Ukendt pris",
            "found_prices": 0,
        }

    except Exception as e:

        print("ANALYZE ERROR:", str(e))

        return {
            "title": "Fejl",
            "material": "Ukendt",
            "condition": "Ukendt",
            "price": "Kunne ikke hente pris",
            "found_prices": 0,
        }