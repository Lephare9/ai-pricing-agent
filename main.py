# main.py

import os
import re
import json
import asyncio
from typing import List, Dict, Any

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ----------------------------
# CORS
# ----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# HELPERS
# ----------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def safe_price(text: str):

    if not text:
        return None

    text = text.replace(".", "")
    text = text.replace(",", ".")
    text = text.replace("kr", "")
    text = text.replace("DKK", "")

    match = re.search(r"(\d+)", text)

    if not match:
        return None

    try:
        return int(match.group(1))
    except:
        return None


# ----------------------------
# DBA
# ----------------------------

class DBAScraper:

    async def search(self, query: str):

        url = f"https://www.dba.dk/soeg/?soeg={query}"

        results = []

        try:

            async with httpx.AsyncClient(timeout=20) as client:

                response = await client.get(
                    url,
                    headers=HEADERS,
                    follow_redirects=True,
                )

            soup = BeautifulSoup(response.text, "html.parser")

            cards = soup.select("article")[:20]

            for card in cards:

                try:

                    text = card.get_text(" ", strip=True)

                    if len(text) < 20:
                        continue

                    title = text[:120]

                    price = None

                    price_match = re.search(
                        r"(\d{2,6})\s*kr",
                        text,
                        re.I
                    )

                    if price_match:
                        price = int(price_match.group(1))

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
                    print("DBA item error:", e)

        except Exception as e:
            print("DBA search failed:", e)

        return results


# ----------------------------
# LAURITZ
# ----------------------------

class LauritzScraper:

    async def search(self, query: str):

        try:

            url = (
                "https://www.lauritz.com/"
                f"da/auctions/search/{query}"
            )

            async with httpx.AsyncClient(timeout=20) as client:

                response = await client.get(
                    url,
                    headers=HEADERS,
                    follow_redirects=True,
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

            # finder __NEXT_DATA__
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

                    results.append({
                        "source": "Lauritz",
                        "title": title,
                        "price": current_bid or estimate,
                        "estimate": estimate,
                        "current_bid": current_bid,
                        "image": image,
                        "url": (
                            f"https://www.lauritz.com/da/auction/{item.get('lotId')}"
                        )
                    })

                except Exception as e:
                    print("Lauritz item parse error:", e)

        except Exception as e:
            print("Lauritz parser failed:", e)

        return results


# ----------------------------
# MARKETPLACE MOCK
# ----------------------------

class MarketplaceScraper:

    async def search(self, query: str):

        # placeholder så hele systemet virker

        return []


# ----------------------------
# AI ENGINE
# ----------------------------

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()
        self.lauritz = LauritzScraper()
        self.marketplace = MarketplaceScraper()

    async def analyze(self, query: str):

        all_results = []

        # DBA
        try:

            dba_results = await self.dba.search(query)

            print("DBA:", len(dba_results))

            all_results.extend(dba_results)

        except Exception as e:
            print("DBA failed:", e)

        # Lauritz
        try:

            lauritz_results = (
                await self.lauritz.get_all_search_results(query)
            )

            print("Lauritz:", len(lauritz_results))

            all_results.extend(lauritz_results)

        except Exception as e:
            print("Lauritz failed:", e)

        # Marketplace
        try:

            market_results = (
                await self.marketplace.search(query)
            )

            print("Marketplace:", len(market_results))

            all_results.extend(market_results)

        except Exception as e:
            print("Marketplace failed:", e)

        print("TOTAL:", len(all_results))

        # filtrer tomme objekter væk
        all_results = [
            x for x in all_results
            if x and x.get("title")
        ]

        # prisberegning
        prices = [
            x["price"]
            for x in all_results
            if x.get("price")
        ]

        estimated_price = None

        if prices:
            estimated_price = int(sum(prices) / len(prices))

        return {
            "success": True,
            "query": query,
            "estimated_price": estimated_price,
            "count": len(all_results),
            "results": all_results[:20],
        }


engine = PricingEngine()

# ----------------------------
# ROUTES
# ----------------------------

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

    # fallback hvis ingen query
    if not final_query:
        final_query = "wegner"

    result = await engine.analyze(final_query)

    return result