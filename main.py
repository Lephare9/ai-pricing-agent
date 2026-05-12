# =========================================================
# main.py
# MODERNE AI PRISAGENT
# Cloudinary + Google Vision + Gemini 2.5 Flash
# DBA + Lauritz
# =========================================================

import os
import re
import json
import statistics

import httpx

from bs4 import BeautifulSoup

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.generativeai as genai


# =========================================================
# CONFIG
# =========================================================

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(
    api_key=GEMINI_API_KEY
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


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
# REQUEST MODEL
# =========================================================

class AnalyzeRequest(BaseModel):
    image_url: str


# =========================================================
# HELPERS
# =========================================================

def safe_int(value):

    if not value:
        return None

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


def median_price(items):

    prices = []

    for item in items:

        price = item.get("price")

        if isinstance(price, int):
            prices.append(price)

    if not prices:
        return None

    return int(statistics.median(prices))


def remove_price_outliers(items):

    cleaned = []

    for item in items:

        price = item.get("price")

        if not price:
            continue

        if price < 50:
            continue

        if price > 250000:
            continue

        cleaned.append(item)

    return cleaned


# =========================================================
# GOOGLE VISION
# =========================================================

async def analyze_with_vision(image_url):

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
                    {"type": "LABEL_DETECTION", "maxResults": 15},
                    {"type": "WEB_DETECTION", "maxResults": 10},
                    {"type": "TEXT_DETECTION"}
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=40) as client:

        response = await client.post(
            url,
            json=payload
        )

    data = response.json()

    result = data["responses"][0]

    labels = []

    for label in result.get("labelAnnotations", []):
        labels.append(label["description"])

    web_entities = []

    web = result.get("webDetection", {})

    for entity in web.get("webEntities", []):

        desc = entity.get("description")

        if desc:
            web_entities.append(desc)

    text = ""

    texts = result.get("textAnnotations", [])

    if texts:
        text = texts[0].get("description", "")

    print("VISION LABELS:", labels)
    print("VISION WEB:", web_entities)
    print("VISION OCR:", text)

    return {
        "labels": labels,
        "web_entities": web_entities,
        "ocr": text
    }


# =========================================================
# GEMINI
# =========================================================

def analyze_with_gemini(image_url):

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        prompt = """

Du analyserer billeder til en dansk AI-prisagent.

VIGTIGT:
90% af objekter er IKKE designermøbler.

Du må IKKE gætte designere.

Du skal først forstå objektet realistisk.

Opgaver:

1. Identificér objektet præcist
2. Identificér kategori
3. Beskriv materialer
4. Beskriv stand
5. Identificér designer/brand KUN hvis sandsynligheden er høj
6. Lav intelligente DBA/Lauritz søgequeries

Svar KUN som JSON.

Format:

{
  "title":"...",
  "category":"...",
  "materials":"...",
  "condition":"...",
  "designer":null,
  "brand":null,
  "designer_confidence":"low",
  "primary_query":"...",
  "secondary_queries":[
    "...",
    "..."
  ]
}

"""

        response = model.generate_content(
            [
                prompt,
                {
                    "file_data": {
                        "mime_type": "image/jpeg",
                        "file_uri": image_url
                    }
                }
            ]
        )

        text = response.text.strip()

        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

        print("GEMINI RAW:", text)

        return json.loads(text)

    except Exception as e:

        print("GEMINI ERROR:", str(e))

        return None


# =========================================================
# SEARCH
# =========================================================

class DBAScraper:

    async def search(self, query):

        url = f"https://www.dba.dk/soeg/?soeg={query}"

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True
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

            price_match = re.search(
                r"(\d[\d\.]*)\s*kr",
                text,
                re.I
            )

            if not price_match:
                continue

            price = safe_int(
                price_match.group(1)
            )

            if not price:
                continue

            title = text[:200]

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
                "url": url
            })

        return results


class LauritzScraper:

    async def search(self, query):

        url = (
            f"https://www.lauritz.com/da/auctions/search/{query}"
        )

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True
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

            price = current_bid or estimate

            if not price:
                continue

            image = item.get(
                "defaultImageUrl"
            )

            if image and not image.startswith("http"):

                image = (
                    "https://images.lauritz.com/"
                    + image
                )

            lot_id = item.get("lotId")

            results.append({
                "source": "Lauritz",
                "title": title,
                "price": price,
                "image": image,
                "url": f"https://www.lauritz.com/da/auction/{lot_id}"
            })

        return results


# =========================================================
# ENGINE
# =========================================================

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()
        self.lauritz = LauritzScraper()

    async def analyze(self, image_url):

        # -------------------------------------------------
        # 1 Vision
        # -------------------------------------------------

        vision_data = await analyze_with_vision(
            image_url
        )

        # -------------------------------------------------
        # 2 Gemini
        # -------------------------------------------------

        gemini_data = analyze_with_gemini(
            image_url
        )

        # fallback hvis Gemini fejler

        if not gemini_data:

            labels = vision_data["labels"]

            primary_query = (
                labels[0]
                if labels
                else "møbel"
            )

            gemini_data = {
                "title": primary_query,
                "category": primary_query,
                "materials": "",
                "condition": "",
                "designer": None,
                "brand": None,
                "designer_confidence": "low",
                "primary_query": primary_query,
                "secondary_queries": []
            }

        primary_query = gemini_data.get(
            "primary_query",
            "møbel"
        )

        secondary_queries = gemini_data.get(
            "secondary_queries",
            []
        )

        # -------------------------------------------------
        # 3 Search queries
        # -------------------------------------------------

        queries = [primary_query]

        for q in secondary_queries:

            if q not in queries:
                queries.append(q)

        print("SEARCH QUERIES:", queries)

        # -------------------------------------------------
        # 4 Search
        # -------------------------------------------------

        all_results = []

        for query in queries[:4]:

            dba_results = await self.dba.search(query)

            print("DBA:", query, len(dba_results))

            all_results.extend(dba_results)

            lauritz_results = await self.lauritz.search(query)

            print("Lauritz:", query, len(lauritz_results))

            all_results.extend(lauritz_results)

        # -------------------------------------------------
        # 5 Cleanup
        # -------------------------------------------------

        all_results = remove_price_outliers(
            all_results
        )

        estimated_price = median_price(
            all_results
        )

        prices = [
            item["price"]
            for item in all_results
            if item.get("price")
        ]

        price_min = None
        price_max = None

        if prices:

            price_min = int(min(prices))
            price_max = int(max(prices))

        # -------------------------------------------------
        # 6 Response
        # -------------------------------------------------

        return {
            "success": True,
            "title": gemini_data.get("title"),
            "category": gemini_data.get("category"),
            "materials": gemini_data.get("materials"),
            "condition": gemini_data.get("condition"),
            "designer": gemini_data.get("designer"),
            "brand": gemini_data.get("brand"),
            "designer_confidence": gemini_data.get("designer_confidence"),
            "query": primary_query,
            "estimated_price": estimated_price,
            "price_min": price_min,
            "price_max": price_max,
            "count": len(all_results),
            "results": all_results[:20]
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
async def analyze(data: AnalyzeRequest):

    if not data.image_url:

        return {
            "success": False,
            "error": "Missing image_url"
        }

    return await engine.analyze(
        data.image_url
    )