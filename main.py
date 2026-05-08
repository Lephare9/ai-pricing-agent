from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from google.cloud import vision

import requests
import statistics
import tempfile
import json
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ---------------------------------------------------
# GOOGLE VISION INIT
# ---------------------------------------------------

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


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------

def clean_text(text):

    if not text:
        return ""

    text = text.lower()

    blacklist = [
        "chair",
        "table",
        "furniture",
        "wood",
        "hardwood",
        "interior",
        "design",
        "room",
        "floor",
        "armrest",
        "stain",
        "yellow",
        "brown",
        "black",
        "grey",
        "white",
        "display",
        "device",
        "electronics",
        "metal",
        "plastic",
        "product",
        "font",
        "material",
        "property",
        "rectangle",
        "parallel",
        "composite material",
        "wood stain",
        "leather",
        "hard",
    ]

    for word in blacklist:
        text = text.replace(word, "")

    text = re.sub(r"[^a-zA-ZæøåÆØÅ0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_prices(text):

    prices = []

    matches = re.findall(
        r'(\d{2,5})\s?(?:kr|,-)',
        text.lower()
    )

    for match in matches:

        try:

            price = int(match)

            if 100 <= price <= 50000:
                prices.append(price)

        except:
            pass

    return prices


# ---------------------------------------------------
# GOOGLE VISION SEARCH
# ---------------------------------------------------

def google_vision_search(image_bytes):

    if not vision_client:
        return [], []

    image = vision.Image(content=image_bytes)

    response = vision_client.web_detection(image=image)

    web = response.web_detection

    queries = []
    urls = []

    try:

        # BEST GUESS LABELS
        for label in web.best_guess_labels:

            text = clean_text(label.label)

            if text:
                queries.append(text)

        # VISUALLY SIMILAR URLS
        for img in web.visually_similar_images[:20]:

            url = img.url.lower()

            if (
                ".dk" in url
                or "dba.dk" in url
                or "facebook.com" in url
                or "guloggratis.dk" in url
            ):
                urls.append(url)

    except Exception as e:

        print("VISION SEARCH ERROR:", str(e))

    return queries, urls


# ---------------------------------------------------
# SERPAPI SEARCH
# ---------------------------------------------------

def serpapi_search(query):

    if not SERPAPI_KEY:
        return []

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "hl": "da",
        "gl": "dk",
        "num": 20,
        "api_key": SERPAPI_KEY,
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    data = response.json()

    prices = []

    for result in data.get("organic_results", []):

        text = (
            result.get("title", "")
            + " "
            + result.get("snippet", "")
        )

        found = extract_prices(text)

        prices.extend(found)

    return prices


# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        # ---------------------------------------------
        # GOOGLE VISION
        # ---------------------------------------------

        queries, urls = google_vision_search(image_bytes)

        print("VISION QUERIES:", queries)
        print("MATCH URLS:", urls)

        # ---------------------------------------------
        # FALLBACK LABELS
        # ---------------------------------------------

        labels = []

        if vision_client:

            image = vision.Image(content=image_bytes)

            response = vision_client.label_detection(image=image)

            labels = [
                clean_text(x.description)
                for x in response.label_annotations[:10]
            ]

            labels = [x for x in labels if x]

        print("LABELS:", labels)

        # ---------------------------------------------
        # BUILD SEARCH QUERY
        # ---------------------------------------------

        if queries:

            search_query = " ".join(queries[:3])

        elif labels:

            search_query = " ".join(labels[:3])

        else:

            search_query = "dansk vintage møbel"

        search_query += " dba facebook marketplace"

        print("SEARCH:", search_query)

        # ---------------------------------------------
        # SEARCH PRICES
        # ---------------------------------------------

        prices = serpapi_search(search_query)

        print("RAW PRICES:", prices)

        # ---------------------------------------------
        # ALSO EXTRACT FROM URLS
        # ---------------------------------------------

        for url in urls:

            prices.extend(extract_prices(url))

        # ---------------------------------------------
        # CLEAN PRICES
        # ---------------------------------------------

        prices = [
            x for x in prices
            if 100 <= x <= 50000
        ]

        print("FILTERED:", prices)

        # remove extreme outliers

        if len(prices) >= 5:

            median = statistics.median(prices)

            prices = [
                p for p in prices
                if median * 0.35 <= p <= median * 2.5
            ]

        # ---------------------------------------------
        # PRICE RESULT
        # ---------------------------------------------

        if len(prices) >= 3:

            median_price = int(statistics.median(prices))

            low = int(median_price * 0.85)
            high = int(median_price * 1.15)

            price_text = f"{low} - {high} kr"

        else:

            price_text = "Ukendt pris"

        # ---------------------------------------------
        # TITLE
        # ---------------------------------------------

        title = "Ukendt møbel"

        if queries:

            title = queries[0].title()

        elif labels:

            title = " ".join(labels[:3]).title()

        # ---------------------------------------------
        # RETURN
        # ---------------------------------------------

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


# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
def root():

    return {
        "status": "running"
    }