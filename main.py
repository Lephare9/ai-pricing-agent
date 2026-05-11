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

    text = text.replace(".", "")
    text = text.replace(",", "")
    text = text.replace("kr.", "")
    text = text.replace("kr", "")
    text = text.replace("DKK", "")

    match = re.search(r"(\d+)", text)

    if not match:
        return None

    try:
        return int(match.group(1))
    except:
        return None


# =========================================================
# DBA
# =========================================================

class DBAScraper:

    async def search(self, query: str):

        results = []

        try:

            url = f"https://www.dba.dk/soeg/?soeg={query}"

            async with httpx.AsyncClient(timeout=20) as client:

                response = await client.get(
                    url,
                    headers=HEADERS,
                    follow_redirects=True
                )

            soup = BeautifulSoup(response.text, "html.parser")

            cards = soup.select("article")

            for card in cards[:20]:

                try:

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
                        "estimate": price,
                        "current_bid": price,
                        "image": image,
                        "url": url,
                    })

                except Exception as e:
                    print("DBA item parse failed:", e)

        except Exception as e:
            print("DBA failed:", e)

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

            async with httpx.AsyncClient(timeout=20) as client:

                response = await client.get(
                    url,
                    headers=HEADERS,
                    follow_redirects=True
                )

            return {
                "success": True,
                "data": response.text
            }

        except Exception as e:

            print("Lauritz failed:", e)

            return {
                "success": False,
                "error": str(e)
            }

    async def get_all_search_results(self, query: str):

        result = await self.search(query)

        if not result["success"]:
            return []

        html = result["data"]

        results = []

        try:

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                html,
                re.DOTALL
            )

            if not match:
                print("No NEXT_DATA found")
                return []

            json_data = json.loads(match.group(1))

            found_items = []

            def recursive_find(obj):

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
                        recursive_find(value)

                elif isinstance(obj, list):

                    for item in obj:
                        recursive_find(item)

            recursive_find(json_data)

            for item in found_items:

                try:

                    title = item.get("title")

                    image = item.get("defaultImageUrl")

                    if image and not image.startswith("http"):
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

                    lot_id = item.get("lotId")

                    results.append({
                        "source": "Lauritz",
                        "title": title,
                        "price": current_bid or estimate,
                        "estimate": estimate,
                        "current_bid": current_bid,
                        "image": image,
                        "url": (
                            f"https://www.lauritz.com/da/auction/{lot_id}"
                        ),
                    })

                except Exception as e:
                    print("Lauritz item failed:", e)

        except Exception as e:
            print("Lauritz parser failed:", e)

        return results


# =========================================================
# MARKETPLACE PLACEHOLDER
# =========================================================

class MarketplaceScraper:

    async def search(self, query: str):

        return []


# =========================================================
# ENGINE
# =========================================================

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()
        self.lauritz = LauritzScraper()
        self.marketplace = MarketplaceScraper()

    async def analyze(self, query: str):

        all_results = []

        # -------------------
        # DBA
        # -------------------

        try:

            dba_results = await self.dba.search(query)

            print("DBA:", len(dba_results))

            all_results.extend(dba_results)

        except Exception as e:
            print("DBA global fail:", e)

        # -------------------
        # Lauritz
        # -------------------

        try:

            lauritz_results = (
                await self.lauritz.get_all_search_results(query)
            )

            print("Lauritz:", len(lauritz_results))

            all_results.extend(lauritz_results)

        except Exception as e:
            print("Lauritz global fail:", e)

        # -------------------
        # Marketplace
        # -------------------

        try:

            market_results = (
                await self.marketplace.search(query)
            )

            print("Marketplace:", len(market_results))

            all_results.extend(market_results)

        except Exception as e:
            print("Marketplace global fail:", e)

        # -------------------
        # FILTER
        # -------------------

        all_results = [
            x for x in all_results
            if x and x.get("title")
        ]

        print("TOTAL:", len(all_results))

        # -------------------
        # PRICE ESTIMATE
        # -------------------

        prices = []

        for item in all_results:

            price = item.get("price")

            if isinstance(price, int):
                prices.append(price)

        estimated_price = None

        if prices:
            estimated_price = int(sum(prices) / len(prices))

        # -------------------
        # NORMALIZE FOR FRONTEND
        # -------------------

        normalized_results = []

        for item in all_results[:20]:

            normalized_results.append({

                # COMMON
                "source": item.get("source"),

                # TITLES
                "name": item.get("title"),
                "title": item.get("title"),

                # PRICE
                "price": item.get("price"),
                "estimated_price": item.get("estimate"),
                "currentBid": item.get("current_bid"),

                # IMAGE
                "image": item.get("image"),
                "imageUrl": item.get("image"),

                # URL
                "url": item.get("url"),

                # DESCRIPTION
                "description": (
                    f"{item.get('source')} - "
                    f"{item.get('title')}"
                ),
            })

        return {

            "success": True,

            "query": query,

            "estimated_price": estimated_price,

            "count": len(normalized_results),

            # MULTI FRONTEND SUPPORT
            "results": normalized_results,
            "items": normalized_results,
            "data": normalized_results,
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

    return await engine.analyze(query)


@app.post("/analyze")
async def analyze(
    query: str = Form(None),
    file: UploadFile = File(None),
):

    final_query = query

    # fallback
    if not final_query:
        final_query = "wegner"

    result = await engine.analyze(final_query)

    return result