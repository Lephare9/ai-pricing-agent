from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import os
import re
import statistics
import requests
from serpapi import GoogleSearch
from google.cloud import vision

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")


# =========================
# GOOGLE VISION
# =========================

vision_client = vision.ImageAnnotatorClient()


# =========================
# HJÆLPERE
# =========================

DANISH_STOPWORDS = [
    "amazon",
    "ebay",
    "etsy",
    "chair",
    "table",
    "furniture",
    "wood",
    "cabinet",
    "black",
    "metal",
    "plastic",
    "display",
    "screen",
    "device",
    "monitor",
    "sofa",
    "lamp",
]


def clean_text(text):
    text = text.lower()

    for bad in DANISH_STOPWORDS:
        text = text.replace(bad, "")

    text = re.sub(r"[^a-zæøå0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_prices(text):
    prices = []

    matches = re.findall(r'(\d{2,5})\s?(kr|dkk)?', text.lower())

    for match in matches:
        try:
            price = int(match[0])

            if 40 <= price <= 50000:
                prices.append(price)

        except:
            pass

    return prices


def filter_prices(prices):
    if not prices:
        return []

    filtered = []

    median = statistics.median(prices)

    for p in prices:
        if median * 0.35 <= p <= median * 2.5:
            filtered.append(p)

    return filtered


def build_price_range(prices):
    if not prices:
        return "Ukendt pris"

    prices = sorted(prices)

    if len(prices) == 1:
        return f"{prices[0]} kr"

    low = int(statistics.quantiles(prices, n=4)[0])
    high = int(statistics.quantiles(prices, n=4)[2])

    if low < 50:
        low = min(prices)

    if high < low:
        high = max(prices)

    return f"{low} – {high} kr"


# =========================
# GOOGLE VISION ANALYSE
# =========================

def analyze_image(image_bytes):

    image = vision.Image(content=image_bytes)

    web_detection = vision_client.web_detection(image=image).web_detection

    labels_response = vision_client.label_detection(image=image)
    labels = [l.description.lower() for l in labels_response.label_annotations]

    print("LABELS:", labels)

    web_entities = []

    if web_detection.web_entities:
        for entity in web_detection.web_entities:

            if entity.description:
                txt = clean_text(entity.description)

                if len(txt) > 2:
                    web_entities.append(txt)

    print("WEB ENTITIES:", web_entities)

    best_title = "Ukendt møbel"

    if web_entities:
        best_title = web_entities[0]

    elif labels:
        best_title = " ".join(labels[:3])

    best_title = clean_text(best_title)

    return {
        "title": best_title,
        "labels": labels,
        "entities": web_entities,
    }


# =========================
# SERPAPI GOOGLE LENS
# =========================

def google_lens_search(image_url):

    params = {
        "engine": "google_lens",
        "url": image_url,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    return results


# =========================
# HENT PRISER FRA LENS
# =========================

def collect_prices(results):

    prices = []

    visual_matches = results.get("visual_matches", [])
    related_content = results.get("related_content", [])
    shopping_results = results.get("shopping_results", [])

    # ===================================
    # VISUAL MATCHES
    # ===================================

    for item in visual_matches[:15]:

        text = ""

        if item.get("title"):
            text += " " + item["title"]

        if item.get("source"):
            text += " " + item["source"]

        if item.get("price"):
            text += " " + str(item["price"])

        found = extract_prices(text)

        prices.extend(found)

    # ===================================
    # RELATED CONTENT
    # ===================================

    for item in related_content[:15]:

        text = ""

        if item.get("title"):
            text += " " + item["title"]

        if item.get("price"):
            text += " " + str(item["price"])

        found = extract_prices(text)

        prices.extend(found)

    # ===================================
    # SHOPPING RESULTS
    # ===================================

    for item in shopping_results[:15]:

        text = ""

        if item.get("title"):
            text += " " + item["title"]

        if item.get("price"):
            text += " " + str(item["price"])

        found = extract_prices(text)

        prices.extend(found)

    print("RAW PRICES:", prices)

    return filter_prices(prices)


# =========================
# ANALYZE
# =========================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        contents = await file.read()

        img = Image.open(io.BytesIO(contents))
        img.thumbnail((1200, 1200))

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)

        image_bytes = buffer.getvalue()

        # ===================================
        # VISION
        # ===================================

        vision_data = analyze_image(image_bytes)

        # ===================================
        # IMGUR GRATIS HOST
        # ===================================

        imgbb_key = os.getenv("IMGBB_KEY")

        image_url = ""

        if imgbb_key:

            import base64

            encoded = base64.b64encode(image_bytes)

            upload = requests.post(
                f"https://api.imgbb.com/1/upload?key={imgbb_key}",
                files={
                    "image": encoded
                },
                timeout=20
            )

            upload_json = upload.json()

            image_url = upload_json["data"]["url"]

        # ===================================
        # GOOGLE LENS
        # ===================================

        prices = []

        if image_url:

            lens_results = google_lens_search(image_url)

            prices = collect_prices(lens_results)

        print("FILTERED:", prices)

        # ===================================
        # RESULTAT
        # ===================================

        if prices:

            price_range = build_price_range(prices)

            final_title = vision_data["title"]

            if final_title == "":
                final_title = "Møbel"

            return {
                "title": final_title.title(),
                "material": "Brugt møbel",
                "condition": "Brugt med almindelige brugsspor",
                "price": price_range,
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
            "title": "Ukendt",
            "material": "Ukendt",
            "condition": "Ukendt",
            "price": "Ukendt pris",
            "found_prices": 0,
        }