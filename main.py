# main.py

import os
import re
import json

import httpx

from bs4 import BeautifulSoup

from fastapi import FastAPI, Form

from fastapi.middleware.cors import CORSMiddleware

from google import genai


# =========================================================
# CONFIG
# =========================================================

GOOGLE_VISION_API_KEY = os.getenv(
    "GOOGLE_VISION_API_KEY"
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# APP
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

def safe_int(value):

    if value is None:
        return None

    if isinstance(value, int):
        return value

    text = str(value)

    text = (
        text
        .replace(".", "")
        .replace(",", "")
        .replace("kr.", "")
        .replace("kr", "")
        .replace("DKK", "")
        .strip()
    )

    match = re.search(r"(\d+)", text)

    if not match:
        return None

    try:
        return int(match.group(1))

    except:
        return None


def average_price(items):

    prices = []

    for item in items:

        price = item.get("price")

        if isinstance(price, int):
            prices.append(price)

    if not prices:
        return None

    return int(sum(prices) / len(prices))


# =========================================================
# GOOGLE VISION
# =========================================================

async def detect_vision(image_url: str):

    url = (
        "https://vision.googleapis.com/v1/images:annotate"
        f"?key={GOOGLE_VISION_API_KEY}"
    )

    payload = {
        "requests": [
            {
                "image": {
                    "source": {
                        "imageUri": image_url
                    }
                },

                "features": [

                    {
                        "type": "WEB_DETECTION",
                        "maxResults": 10
                    },

                    {
                        "type": "LABEL_DETECTION",
                        "maxResults": 10
                    },

                    {
                        "type": "TEXT_DETECTION",
                        "maxResults": 10
                    }

                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as client:

        response = await client.post(
            url,
            json=payload
        )

    data = response.json()

    response_data = (
        data.get("responses", [{}])[0]
    )

    # =====================================================
    # WEB ENTITIES
    # =====================================================

    web_entities_raw = (
        response_data.get(
            "webDetection",
            {}
        ).get(
            "webEntities",
            []
        )
    )

    web_entities = []

    for entity in web_entities_raw:

        name = (
            entity.get("description", "")
            .lower()
            .strip()
        )

        score = entity.get("score", 0)

        if (
            name
            and score > 0.5
            and len(name) > 2
        ):
            web_entities.append(name)

    # =====================================================
    # LABELS
    # =====================================================

    labels_raw = (
        response_data.get(
            "labelAnnotations",
            []
        )
    )

    labels = []

    for label in labels_raw:

        name = (
            label.get("description", "")
            .lower()
            .strip()
        )

        if name:
            labels.append(name)

    # =====================================================
    # OCR
    # =====================================================

    texts = []

    text_annotations = (
        response_data.get(
            "textAnnotations",
            []
        )
    )

    for item in text_annotations[:5]:

        text = (
            item.get("description", "")
            .lower()
            .strip()
        )

        if text:
            texts.append(text)

    print("VISION WEB ENTITIES:")
    print(web_entities)

    print("VISION LABELS:")
    print(labels)

    print("VISION OCR:")
    print(texts)

    return {

        "web_entities": web_entities,

        "labels": labels,

        "texts": texts,
    }


# =========================================================
# GEMINI OBJECT UNDERSTANDING
# =========================================================

async def detect_with_gemini(image_url: str):

    try:

        response = gemini_client.models.generate_content(

            model="gemini-2.0-flash",

            contents=[

                {
                    "role": "user",

                    "parts": [

                        {
                            "text":
                            """
Describe this object for Danish secondhand marketplace search.

Return ONLY short keywords.

Focus on:
- object type
- style
- material
- designer
- model

Max 12 words.
                            """
                        },

                        {
                            "file_data": {
                                "file_uri": image_url
                            }
                        }

                    ]
                }

            ]
        )

        text = response.text.strip().lower()

        print("GEMINI:")
        print(text)

        return text

    except Exception as e:

        print("GEMINI FAILED:")
        print(e)

        return ""


# =========================================================
# QUERY BUILDER
# =========================================================

def build_search_query(

    vision_data,
    gemini_text

):

    parts = []

    # =====================================================
    # GEMINI FIRST
    # =====================================================

    if gemini_text:

        parts.extend(
            gemini_text.split()
        )

    # =====================================================
    # WEB ENTITIES
    # =====================================================

    for item in vision_data["web_entities"]:

        item = item.lower()

        if len(item) < 3:
            continue

        parts.extend(
            item.split()
        )

    # =====================================================
    # LABELS (LOW PRIORITY)
    # =====================================================

    bad_words = [

        "wood",
        "plywood",
        "hardwood",
        "flooring",
        "varnish",
        "steel",
        "plank",
        "material",
        "brown",
        "rectangle",
        "line",
        "floor",
    ]

    translations = {

        "chair": "stol",
        "bar stool": "barstol",
        "table": "bord",
        "lamp": "lampe",
        "sofa": "sofa",
        "armchair": "lænestol",
    }

    for label in vision_data["labels"]:

        label = label.lower()

        if label in bad_words:
            continue

        if label in translations:

            parts.append(
                translations[label]
            )

    # =====================================================
    # CLEANUP
    # =====================================================

    cleaned = []

    seen = set()

    for word in parts:

        word = (
            word
            .replace(",", "")
            .replace(".", "")
            .strip()
            .lower()
        )

        if len(word) < 2:
            continue

        if word in seen:
            continue

        seen.add(word)

        cleaned.append(word)

    # fallback

    if not cleaned:
        return "design møbel"

    final_query = " ".join(
        cleaned[:10]
    )

    print("FINAL QUERY:")
    print(final_query)

    return final_query


# =========================================================
# DBA
# =========================================================

class DBAScraper:

    async def search(self, query: str):

        url = (
            f"https://www.dba.dk/soeg/?soeg={query}"
        )

        async with httpx.AsyncClient(timeout=20) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True,
            )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        cards = soup.select("article")

        for card in cards[:20]:

            text = card.get_text(
                " ",
                strip=True
            )

            if len(text) < 20:
                continue

            title = text[:160]

            price = None

            price_match = re.search(
                r"(\d[\d\.]*)\s*kr",
                text,
                re.I
            )

            if price_match:

                price = safe_int(
                    price_match.group(1)
                )

            image = None

            img = card.select_one("img")

            if img:

                image = (
                    img.get("src")
                    or img.get("data-src")
                )

            results.append({

                "source": "DBA",

                "title": title,

                "price": price,

                "image": image,

                "url": url,
            })

        return results


# =========================================================
# LAURITZ
# =========================================================

class LauritzScraper:

    async def search(self, query: str):

        url = (
            f"https://www.lauritz.com/da/auctions/search/{query}"
        )

        async with httpx.AsyncClient(timeout=20) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True,
            )

        html = response.text

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL
        )

        if not match:
            return []

        data = json.loads(
            match.group(1)
        )

        found_items = []

        def walk(obj):

            if isinstance(obj, dict):

                if (
                    "title" in obj
                    and (
                        "lotId" in obj
                        or "auctionId" in obj
                    )
                ):
                    found_items.append(obj)

                for value in obj.values():
                    walk(value)

            elif isinstance(obj, list):

                for item in obj:
                    walk(item)

        walk(data)

        results = []

        for item in found_items:

            title = item.get("title")

            if not title:
                continue

            image = item.get(
                "defaultImageUrl"
            )

            if (
                image
                and not image.startswith("http")
            ):
                image = (
                    f"https://images.lauritz.com/{image}"
                )

            prices = item.get("prices", {})

            estimate = (
                prices.get("estimated", {})
                .get("showroom", {})
                .get("amount")
            )

            current_bid = (
                prices.get("currentBid", {})
                .get("showroom", {})
                .get("amount")
            )

            price = (
                current_bid
                or estimate
            )

            lot_id = item.get("lotId")

            results.append({

                "source": "Lauritz",

                "title": title,

                "price": price,

                "image": image,

                "url": (
                    f"https://www.lauritz.com/da/auction/{lot_id}"
                ),
            })

        return results


# =========================================================
# RELEVANCE SCORING
# =========================================================

def score_results(results, query):

    query_words = query.lower().split()

    for item in results:

        score = 0

        title = (
            item.get("title", "")
            .lower()
        )

        for word in query_words:

            if word in title:
                score += 5

        item["score"] = score

    results.sort(
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    return results


# =========================================================
# ENGINE
# =========================================================

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()

        self.lauritz = LauritzScraper()

    async def analyze(self, image_url: str):

        # =====================================================
        # GOOGLE VISION
        # =====================================================

        vision_data = await detect_vision(
            image_url
        )

        # =====================================================
        # GEMINI
        # =====================================================

        gemini_text = await detect_with_gemini(
            image_url
        )

        # =====================================================
        # QUERY
        # =====================================================

        query = build_search_query(

            vision_data,
            gemini_text
        )

        # =====================================================
        # SCRAPERS
        # =====================================================

        all_results = []

        # DBA

        try:

            dba_results = await self.dba.search(
                query
            )

            print(
                "DBA:",
                len(dba_results)
            )

            all_results.extend(
                dba_results
            )

        except Exception as e:

            print("DBA FAILED:")
            print(e)

        # Lauritz

        try:

            lauritz_results = (
                await self.lauritz.search(
                    query
                )
            )

            print(
                "Lauritz:",
                len(lauritz_results)
            )

            all_results.extend(
                lauritz_results
            )

        except Exception as e:

            print("LaurITZ FAILED:")
            print(e)

        # =====================================================
        # CLEANUP
        # =====================================================

        all_results = [

            item for item in all_results

            if item.get("title")
        ]

        # =====================================================
        # RELEVANCE
        # =====================================================

        all_results = score_results(

            all_results,
            query
        )

        # =====================================================
        # PRICE
        # =====================================================

        estimated_price = average_price(
            all_results[:10]
        )

        print("TOTAL:")
        print(len(all_results))

        print("ESTIMATED PRICE:")
        print(estimated_price)

        # =====================================================
        # RESPONSE
        # =====================================================

        return {

            "success": True,

            "query": query,

            "gemini": gemini_text,

            "vision": vision_data,

            "estimated_price": estimated_price,

            "count": len(all_results),

            "results": all_results[:20],
        }


engine = PricingEngine()


# =========================================================
# ROUTES
# =========================================================

@app.get("/")
async def root():

    return {
        "status": "running"
    }


@app.post("/analyze")
async def analyze(

    image_url: str = Form(None),

):

    if not image_url:

        return {

            "success": False,

            "error": "Missing image_url"
        }

    result = await engine.analyze(
        image_url
    )

    return result