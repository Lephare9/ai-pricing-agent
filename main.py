import os
import re
import json

import httpx

from bs4 import BeautifulSoup

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel


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

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

GOOGLE_VISION_API_KEY = os.getenv(
    "GOOGLE_VISION_API_KEY"
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

async def detect_labels(image_url: str):

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
                        "type": "LABEL_DETECTION",
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

    labels = (
        data.get("responses", [{}])[0]
        .get("labelAnnotations", [])
    )

    names = []

    for label in labels:

        name = (
            label.get("description", "")
            .lower()
        )

        if name:
            names.append(name)

    return names


# =========================================================
# QUERY CLEANUP
# =========================================================

def build_search_query(labels):

    PRIORITY = [
        "lamp",
        "chair",
        "table",
        "sofa",
        "lighting",
        "furniture",
    ]

    for word in PRIORITY:

        for label in labels:

            if word in label:
                return word

    if labels:
        return labels[0]

    return "furniture"


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

            if not price:
                continue

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

            prices = item.get(
                "prices",
                {}
            )

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

            if (
                image
                and not image.startswith("http")
            ):
                image = (
                    f"https://images.lauritz.com/{image}"
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
# ENGINE
# =========================================================

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()
        self.lauritz = LauritzScraper()

    async def analyze(self, image_url: str):

        labels = await detect_labels(
            image_url
        )

        print("VISION LABELS:", labels)

        query = build_search_query(
            labels
        )

        print("SEARCH QUERY:", query)

        all_results = []

        dba_results = await self.dba.search(
            query
        )

        print("DBA:", len(dba_results))

        lauritz_results = await self.lauritz.search(
            query
        )

        print("Lauritz:", len(lauritz_results))

        all_results.extend(dba_results)
        all_results.extend(lauritz_results)

        estimated_price = average_price(
            all_results
        )

        return {
            "success": True,
            "query": query,
            "labels": labels,
            "estimated_price": estimated_price,
            "count": len(all_results),
            "results": all_results[:10],
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