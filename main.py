from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from google.cloud import vision

import requests
import statistics
import tempfile
import json
import os
import re
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
IMGBB_KEY = os.getenv("IMGBB_KEY")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")


# -----------------------------
# GOOGLE VISION AUTH
# -----------------------------

vision_client = None

try:

    if GOOGLE_CREDS_JSON:

        creds_dict = json.loads(GOOGLE_CREDS_JSON)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False
        ) as f:

            json.dump(creds_dict, f)
            creds_path = f.name

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

        vision_client = vision.ImageAnnotatorClient()

        print("GOOGLE VISION READY")

    else:
        print("GOOGLE_CREDS_JSON missing")

except Exception as e:
    print("VISION INIT ERROR:", str(e))


# -----------------------------
# HELPERS
# -----------------------------

def clean_text(text):

    if not text:
        return ""

    text = text.lower()

    blacklist = [
        "chair",
        "table",
        "wood",
        "furniture",
        "metal",
        "display device",
        "flat panel display",
        "plastic",
        "silver",
        "grey",
        "black",
        "interior design",
        "home decor",
        "product",
        "room",
    ]

    for word in blacklist:
        text = text.replace(word, "")

    text = re.sub(r"[^a-zA-ZæøåÆØÅ0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_prices(text):

    prices = []

    matches = re.findall(r'(\d{2,5})\s?(?:kr|,-)', text.lower())

    for match in matches:

        try:

            price = int(match)

            if 50 <= price <= 50000:
                prices.append(price)

        except:
            pass

    return prices


def upload_to_imgbb(image_bytes):

    if not IMGBB_KEY:
        raise Exception("IMGBB_KEY mangler")

    encoded = base64.b64encode(image_bytes).decode()

    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={
            "key": IMGBB_KEY,
            "image": encoded
        },
        timeout=30
    )

    data = response.json()

    return data["data"]["url"]


def google_vision_search(image_bytes):

    if not vision_client:
        return []

    image = vision.Image(content=image_bytes)

    response = vision_client.web_detection(image=image)

    results = []

    try:

        web = response.web_detection

        for page in web.pages_with_matching_images[:10]:

            url = page.url.lower()

            if (
                ".dk" in url
                or "dba.dk" in url
                or "facebook.com" in url
                or "guloggratis.dk" in url
            ):
                results.append(url)

    except Exception as e:
        print("VISION SEARCH ERROR:", str(e))

    return results


def serpapi_search(query):

    if not SERPAPI_KEY:
        return []

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "hl": "da",
        "gl": "dk",
        "api_key": SERPAPI_KEY,
    }

    response = requests.get(url, params=params, timeout=30)

    data = response.json()

    prices = []

    for result in data.get("organic_results", []):

        snippet = (
            result.get("snippet", "")
            + " "
            + result.get("title", "")
        )

        prices.extend(extract_prices(snippet))

    return prices


# -----------------------------
# MAIN ANALYZE
# -----------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        # -----------------------------
        # GOOGLE VISION LABELS
        # -----------------------------

        labels = []

        title = "Ukendt møbel"

        if vision_client:

            image = vision.Image(content=image_bytes)

            response = vision_client.label_detection(image=image)

            labels = [
                clean_text(label.description)
                for label in response.label_annotations[:8]
            ]

            labels = [x for x in labels if x]

            print("LABELS:", labels)

        # -----------------------------
        # WEB DETECTION
        # -----------------------------

        urls = google_vision_search(image_bytes)

        print("MATCH URLS:", urls)

        # -----------------------------
        # BUILD DANISH SEARCH
        # -----------------------------

        search_query = " ".join(labels[:4])

        if not search_query:
            search_query = "dansk møbel"

        search_query += " brugt dba facebook marketplace"

        print("SEARCH:", search_query)

        # -----------------------------
        # SERPAPI
        # -----------------------------

        prices = serpapi_search(search_query)

        print("RAW PRICES:", prices)

        # -----------------------------
        # FALLBACK FROM URL TEXT
        # -----------------------------

        for url in urls:

            prices.extend(extract_prices(url))

        # -----------------------------
        # CLEAN PRICES
        # -----------------------------

        prices = [
            p for p in prices
            if 100 <= p <= 25000
        ]

        print("FILTERED:", prices)

        if len(prices) >= 3:

            median_price = int(statistics.median(prices))

            low = int(median_price * 0.8)
            high = int(median_price * 1.2)

            price_text = f"{low} - {high} kr"

        else:

            price_text = "Ukendt pris"

        # -----------------------------
        # TITLE
        # -----------------------------

        if labels:
            title = " ".join(labels[:3]).title()

        return {
            "title": title,
            "material": "Brugt",
            "condition": "Almindelige brugsspor",
            "price": price_text,
            "found_prices": len(prices),
        }

    except Exception as e:

        import traceback

        traceback.print_exc()

        return {
            "title": "Fejl",
            "material": "Ukendt",
            "condition": str(e),
            "price": "Kunne ikke hente pris",
            "found_prices": 0,
        }


@app.get("/")
def root():
    return {"status": "running"}