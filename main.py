from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import asyncio

app = FastAPI(title="AI Pricing Agent")


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Lauritz scraper
# =========================

BASE_URL = "https://www.lauritz.com/_next/data"


class LauritzScraper:

    def __init__(self):
        self.build_id = None

    async def get_build_id(self):

        if self.build_id:
            return self.build_id

        url = "https://www.lauritz.com/da/auctions/search/wegner"

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(url)

            text = response.text

            marker = '"buildId":"'

            if marker in text:

                start = text.find(marker) + len(marker)
                end = text.find('"', start)

                self.build_id = text[start:end]

                return self.build_id

        raise Exception("Could not find buildId")

    async def search(self, query: str):

        build_id = await self.get_build_id()

        url = (
            f"{BASE_URL}/{build_id}/da/auctions/search/{query}.json"
            f"?query={query}"
        )

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(url)

            if response.status_code != 200:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "url": url,
                    "text": response.text[:500]
                }

            data = response.json()

            return {
                "success": True,
                "url": url,
                "data": data
            }

    async def get_all_search_results(self, query: str):

        result = await self.search(query)

        if not result["success"]:
            return []

        data = result["data"]

        auctions = []

        # Forsøg forskellige paths
        possible_paths = [
            ["pageProps", "auctions"],
            ["pageProps", "searchResult", "auctions"],
            ["pageProps", "results"],
            ["pageProps", "items"],
        ]

        for path in possible_paths:

            current = data

            found = True

            for key in path:

                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    found = False
                    break

            if found and isinstance(current, list):
                auctions = current
                break

        return auctions


lauritz = LauritzScraper()


# =========================
# Models
# =========================

class AnalyzeRequest(BaseModel):
    query: str


# =========================
# Routes
# =========================

@app.get("/")
async def root():

    return {
        "success": True,
        "service": "AI Pricing Agent",
        "status": "running"
    }


@app.get("/health")
async def health():

    return {
        "status": "ok"
    }


@app.get("/search")
async def search(query: str):

    results = await lauritz.get_all_search_results(query)

    simplified = []

    for lot in results[:20]:

        simplified.append({
            "title": lot.get("title"),
            "lotId": lot.get("lotId"),
            "image": lot.get("defaultImageUrl"),
            "currentBid": (
                lot.get("prices", {})
                .get("currentBid", {})
                .get("showroom", {})
                .get("amount")
            ),
            "estimate": (
                lot.get("prices", {})
                .get("estimated", {})
                .get("showroom", {})
                .get("amount")
            ),
        })

    return {
        "success": True,
        "query": query,
        "count": len(simplified),
        "results": simplified,
    }


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):

    results = await lauritz.get_all_search_results(request.query)

    simplified = []

    for lot in results[:20]:

        simplified.append({
            "title": lot.get("title"),
            "lotId": lot.get("lotId"),
            "image": lot.get("defaultImageUrl"),
            "currentBid": (
                lot.get("prices", {})
                .get("currentBid", {})
                .get("showroom", {})
                .get("amount")
            ),
            "estimate": (
                lot.get("prices", {})
                .get("estimated", {})
                .get("showroom", {})
                .get("amount")
            ),
        })

    return {
        "success": True,
        "query": request.query,
        "count": len(simplified),
        "results": simplified,
    }


@app.get("/debug")
async def debug(query: str = "wegner"):

    result = await lauritz.search(query)

    return result