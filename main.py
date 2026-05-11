# main.py

import re
import json
from typing import List, Dict, Any

import httpx
from bs4 import BeautifulSoup

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware


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
# DBA
# =========================================================

class DBAScraper:

    async def search(self, query: str):

        url = f"https://www.dba.dk/soeg/?soeg={query}"

        async with httpx.AsyncClient(timeout=20) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True,
            )

        soup = BeautifulSoup(response.text, "html.parser")

        results = []

        cards = soup.select("article")

        for card in cards[:20]:

            text = card.get_text(" ", strip=True)

            if len(text) < 20:
                continue

            title = text[:120]

            price = None

            price_match = re.search(
                r"(\d[\d\.]*)\s*kr",
                text,
                re.I
            )

            if price_match:
                price = safe_int(price_match.group(1))

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

            image = item.get("defaultImageUrl")

            if image and not image.startswith("http"):
                image = f"https://images.lauritz.com/{image}"

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

    async def analyze(self, query: str):

        all_results = []

        # DBA

        dba_results = await self.dba.search(query)

        print("DBA:", len(dba_results))

        all_results.extend(dba_results)

        # Lauritz

        lauritz_results = await self.lauritz.search(query)

        print("Lauritz:", len(lauritz_results))

        all_results.extend(lauritz_results)

        # Cleanup

        all_results = [
            item for item in all_results
            if item.get("title")
        ]

        print("TOTAL:", len(all_results))

        estimated_price = average_price(all_results)

        return {
            "success": True,
            "query": query,
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


@app.get("/search")
async def search(query: str):

    if not query:

        return {
            "success": False,
            "error": "Missing query"
        }

    return await engine.analyze(query)


@app.post("/analyze")
async def analyze(
    query: str = Form(None),
    file: UploadFile = File(None),
):

    # IMPORTANT:
    # No fake fallback anymore

    if not query:

        return {
            "success": False,
            "error": "No query detected"
        }

    result = await engine.analyze(query)

    return result