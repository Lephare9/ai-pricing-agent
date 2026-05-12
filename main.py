# =========================================================
# AI PRICING AGENT
# Cloudinary -> Vision -> Gemini 2.5 Flash -> DBA/Lauritz
# =========================================================

import os
import re
import json
import httpx

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware

from bs4 import BeautifulSoup

import google.generativeai as genai


# =========================================================
# CONFIG
# =========================================================

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

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
# HELPERS
# =========================================================

def safe_int(value):

    if not value:
        return None

    if isinstance(value, int):
        return value

    text = (
        str(value)
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

async def detect_with_vision(image_url: str):

    url = (
        f"https://vision.googleapis.com/v1/images:annotate"
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
                        "type": "LABEL_DETECTION",
                        "maxResults": 15
                    },
                    {
                        "type": "WEB_DETECTION",
                        "maxResults": 10
                    },
                    {
                        "type": "OBJECT_LOCALIZATION",
                        "maxResults": 10
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=60) as client:

        response = await client.post(
            url,
            json=payload
        )

    data = response.json()

    try:

        annotations = data["responses"][0]

        labels = [
            x["description"]
            for x in annotations.get("labelAnnotations", [])
        ]

        web_entities = [
            x.get("description", "")
            for x in (
                annotations
                .get("webDetection", {})
                .get("webEntities", [])
            )
        ]

        objects = [
            x.get("name", "")
            for x in (
                annotations
                .get("localizedObjectAnnotations", [])
            )
        ]

        return {
            "labels": labels,
            "web_entities": web_entities,
            "objects": objects,
        }

    except Exception as e:

        print("VISION ERROR:", e)

        return {
            "labels": [],
            "web_entities": [],
            "objects": [],
        }


# =========================================================
# GEMINI 2.5 FLASH
# =========================================================

async def detect_with_gemini(image_url: str):

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        prompt = """
        Analyze this image.

        Identify:
        - object type
        - furniture category
        - possible designer
        - possible brand
        - materials
        - style

        Return ONLY valid JSON:

        {
          "object_type": "",
          "category": "",
          "designer": "",
          "brand": "",
          "materials": [],
          "style": "",
          "search_query": ""
        }
        """

        response = model.generate_content([
            prompt,
            {
                "mime_type": "image/jpeg",
                "uri": image_url
            }
        ])

        text = response.text.strip()

        text = (
            text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        data = json.loads(text)

        print("GEMINI:", data)

        return data

    except Exception as e:

        print("GEMINI ERROR:", e)

        return {
            "object_type": "",
            "category": "",
            "designer": "",
            "brand": "",
            "materials": [],
            "style": "",
            "search_query": ""
        }


# =========================================================
# QUERY BUILDER
# =========================================================

def build_search_query(vision_data, gemini_data):

    query_parts = []

    if gemini_data.get("designer"):
        query_parts.append(
            gemini_data["designer"]
        )

    if gemini_data.get("brand"):
        query_parts.append(
            gemini_data["brand"]
        )

    if gemini_data.get("object_type"):
        query_parts.append(
            gemini_data["object_type"]
        )

    if gemini_data.get("category"):
        query_parts.append(
            gemini_data["category"]
        )

    if not query_parts:

        entities = vision_data.get(
            "web_entities",
            []
        )

        if entities:
            query_parts.append(entities[0])

    if not query_parts:

        labels = vision_data.get(
            "labels",
            []
        )

        allowed = [
            "chair",
            "lamp",
            "table",
            "sofa",
            "cabinet",
            "barrel",
            "wine barrel",
            "stool",
            "vase",
            "desk",
            "shelf"
        ]

        for label in labels:

            lower = label.lower()

            if lower in allowed:
                query_parts.append(lower)
                break

    if not query_parts:
        query_parts.append("møbel")

    query = " ".join(query_parts)

    print("SEARCH QUERY:", query)

    return query


# =========================================================
# DBA
# =========================================================

class DBAScraper:

    async def search(self, query: str):

        url = f"https://www.dba.dk/soeg/?soeg={query}"

        async with httpx.AsyncClient(timeout=30) as client:

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

            try:

                text = card.get_text(
                    " ",
                    strip=True
                )

                if len(text) < 20:
                    continue

                title = text[:140]

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

            except Exception as e:
                print("DBA ITEM ERROR:", e)

        print("DBA:", len(results))

        return results


# =========================================================
# LAURITZ
# =========================================================

class LauritzScraper:

    async def search(self, query: str):

        try:

            url = (
                f"https://www.lauritz.com/da/auctions/search/{query}"
            )

            async with httpx.AsyncClient(timeout=30) as client:

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

            data = json.loads(match.group(1))

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

                if image and not image.startswith("http"):
                    image = (
                        f"https://images.lauritz.com/{image}"
                    )

                prices = item.get("prices", {})

                estimate = (
                    prices
                    .get("estimated", {})
                    .get("showroom", {})
                    .get("amount")
                )

                current_bid = (
                    prices
                    .get("currentBid", {})
                    .get("showroom", {})
                    .get("amount")
                )

                price = current_bid or estimate

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

            print("Lauritz:", len(results))

            return results

        except Exception as e:

            print("LAURITZ ERROR:", e)

            return []


# =========================================================
# ENGINE
# =========================================================

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()
        self.lauritz = LauritzScraper()

    async def analyze(self, image_url: str):

        vision_data = await detect_with_vision(
            image_url
        )

        print(
            "VISION LABELS:",
            vision_data["labels"]
        )

        gemini_data = await detect_with_gemini(
            image_url
        )

        query = build_search_query(
            vision_data,
            gemini_data
        )

        all_results = []

        dba_results = await self.dba.search(
            query
        )

        lauritz_results = await self.lauritz.search(
            query
        )

        all_results.extend(dba_results)
        all_results.extend(lauritz_results)

        estimated_price = average_price(
            all_results
        )

        return {
            "success": True,
            "query": query,
            "estimated_price": estimated_price,
            "count": len(all_results),
            "results": all_results[:20],
            "vision": vision_data,
            "gemini": gemini_data,
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
async def analyze(payload: dict = Body(...)):

    image_url = payload.get("image_url")

    if not image_url:

        return {
            "success": False,
            "error": "Missing image_url"
        }

    result = await engine.analyze(
        image_url
    )

    return result