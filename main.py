import asyncio
import json
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, Query

app = FastAPI(title="Lauritz JSON Scraper")

NEXT_DATA_BUILD = "c6d54380ce11bdfd158cb090e4e781681c29f590"
BASE_URL = "https://www.lauritz.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}


class LauritzClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=30,
            follow_redirects=True,
        )

    async def close(self):
        await self.client.aclose()

    async def search(
        self,
        query: str,
        take: int = 60,
        skip: int = 0,
        category_id: int = 55,
    ) -> Dict:
        url = (
            f"{BASE_URL}/_next/data/{NEXT_DATA_BUILD}"
            f"/da/auctions/search/{query}.json"
        )

        params = {
            "categoryId": category_id,
            "isAuction": "true",
            "isActive": "true",
            "newItem": "true",
            "usedItem": "true",
            "sortType": "score",
            "sortDirection": "desc",
            "take": take,
            "skip": skip,
            "query": query,
        }

        response = await self.client.get(url, params=params)
        response.raise_for_status()

        return response.json()

    async def get_auction(self, slug: str, lot_id: int) -> Dict:
        url = (
            f"{BASE_URL}/_next/data/{NEXT_DATA_BUILD}"
            f"/da/auction/{slug}/{lot_id}.json"
        )

        params = {
            "slug": slug,
            "id": lot_id,
        }

        response = await self.client.get(url, params=params)
        response.raise_for_status()

        return response.json()

    async def get_all_search_results(self, query: str) -> List[Dict]:
        all_lots = []
        skip = 0
        take = 60

        while True:
            data = await self.search(query=query, take=take, skip=skip)

            auctions = (
                data.get("pageProps", {})
                .get("auctions", {})
                .get("lots", [])
            )

            if not auctions:
                break

            all_lots.extend(auctions)

            if len(auctions) < take:
                break

            skip += take

        return all_lots


lauritz = LauritzClient()


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Lauritz JSON scraper",
    }


@app.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    details: bool = Query(False, description="Fetch full auction details"),
):
    lots = await lauritz.get_all_search_results(q)

    if not details:
        return {
            "query": q,
            "count": len(lots),
            "lots": lots,
        }

    detailed_results = []

    for lot in lots:
        lot_id = lot.get("lotId")

        title = lot.get("title", "")
        slug = (
            title.lower()
            .replace(".", "")
            .replace(":", "")
            .replace(",", "")
            .replace("/", "-")
            .replace(" ", "-")
            .replace("æ", "ae")
            .replace("ø", "oe")
            .replace("å", "aa")
        )

        try:
            detail = await lauritz.get_auction(slug=slug, lot_id=lot_id)
            detailed_results.append(detail)
        except Exception as e:
            detailed_results.append(
                {
                    "lotId": lot_id,
                    "error": str(e),
                }
            )

    return {
        "query": q,
        "count": len(detailed_results),
        "results": detailed_results,
    }


@app.get("/search/simple")
async def simple_search(q: str):
    lots = await lauritz.get_all_search_results(q)

    simplified = []

    for lot in lots:
        simplified.append(
            {
                "lotId": lot.get("lotId"),
                "title": lot.get("title"),
                "image": lot.get("defaultImageUrl"),
                "estimate": lot.get("prices", {})
                .get("estimatedPrice", {})
                .get("showroom", {})
                .get("amount"),
                "currentBid": lot.get("prices", {})
                .get("currentBidPrice", {})
                .get("showroom", {})
                .get("amount"),
                "auctionId": lot.get("auctionId"),
                "showroom": lot.get("showroom", {}).get("name"),
            }
        )

    return {
        "query": q,
        "count": len(simplified),
        "results": simplified,
    }


@app.on_event("shutdown")
async def shutdown_event():
    await lauritz.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
