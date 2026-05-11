# main.py

import os
import re
import json
import base64

import httpx
import cloudinary
import cloudinary.uploader

from bs4 import BeautifulSoup

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
)

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
# CLOUDINARY
# =========================================================

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
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

class VisionService:

    def __init__(self):

        self.api_key = os.getenv("GOOGLE_VISION_API_KEY")

    async def detect_query(self, image_bytes: bytes):

        if not self.api_key:
            return None

        try:

            image_base64 = base64.b64encode(
                image_bytes
            ).decode("utf-8")

            url = (
                "https://vision.googleapis.com/v1/images:annotate"
                f"?key={self.api_key}"
            )

            payload = {
                "requests": [
                    {
                        "image": {
                            "content": image_base64
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
                                "type": "OBJECT_LOCALIZATION",
                                "maxResults": 10
                            },
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

            responses = data.get("responses", [])

            if not responses:
                return None

            result = responses[0]

            # =================================================
            # WEB ENTITIES FIRST (BEST FOR DESIGN / BRANDS)
            # =================================================

            web_entities = (
                result.get("webDetection", {})
                .get("webEntities", [])
            )

            candidates = []

            for entity in web_entities:

                description = entity.get("description")
                score = entity.get("score", 0)

                if not description:
                    continue

                description = description.strip()

                if len(description) < 3:
                    continue

                candidates.append({
                    "text": description,
                    "score": score
                })

            # =================================================
            # LABELS
            # =================================================

            labels = result.get(
                "labelAnnotations",
                []
            )

            for label in labels:

                description = label.get("description")
                score = label.get("score", 0)

                if not description:
                    continue

                candidates.append({
                    "text": description,
                    "score": score
                })

            # =================================================
            # OBJECTS
            # =================================================

            objects = result.get(
                "localizedObjectAnnotations",
                []
            )

            for obj in objects:

                name = obj.get("name")
                score = obj.get("score", 0)

                if not name:
                    continue

                candidates.append({
                    "text": name,
                    "score": score
                })

            # =================================================
            # SORT BEST MATCH
            # =================================================

            candidates.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            # =================================================
            # REMOVE BAD GENERIC TERMS
            # =================================================

            blocked = {
                "wood",
                "hardwood",
                "floor",
                "room",
                "interior design",
                "rectangle",
                "font",
                "material",
                "brown",
                "table",
                "furniture",
            }

            for candidate in candidates:

                text = candidate["text"].lower()

                if text in blocked:
                    continue

                if len(text) < 3:
                    continue

                return text

            return None

        except Exception as e:

            print("VISION FAILED:", e)

            return None


# =========================================================
# DBA
# =========================================================

class DBAScraper:

    async def search(self, query: str):

        try:

            url = f"https://www.dba.dk/soeg/?soeg={query}"

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

            return results

        except Exception as e:

            print("DBA FAILED:", e)

            return []


# =========================================================
# LAURITZ
# =========================================================

class LauritzScraper:

    async def search(self, query: str):

        try:

            url = (
                "https://www.lauritz.com/da/"
                f"auctions/search/{query}"
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

                image = item.get(
                    "defaultImageUrl"
                )

                if (
                    image
                    and not image.startswith("http")
                ):
                    image = (
                        "https://images.lauritz.com/"
                        f"{image}"
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

                price = current_bid or estimate

                lot_id = item.get("lotId")

                results.append({
                    "source": "Lauritz",
                    "title": title,
                    "price": price,
                    "image": image,
                    "url": (
                        "https://www.lauritz.com/da/"
                        f"auction/{lot_id}"
                    ),
                })

            return results

        except Exception as e:

            print("LAURITZ FAILED:", e)

            return []


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

        # CLEANUP

        all_results = [
            item for item in all_results
            if item.get("title")
        ]

        print("TOTAL:", len(all_results))

        estimated_price = average_price(
            all_results
        )

        return {
            "success": True,
            "query": query,
            "estimated_price": estimated_price,
            "count": len(all_results),
            "results": all_results[:20],
        }


engine = PricingEngine()
vision = VisionService()


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

    final_query = query

    # =====================================================
    # IMAGE ANALYSIS
    # =====================================================

    if not final_query and file:

        try:

            image_bytes = await file.read()

            print(
                "IMAGE RECEIVED:",
                len(image_bytes),
                "bytes"
            )

            # =============================================
            # CLOUDINARY RESIZE
            # =============================================

            upload_result = cloudinary.uploader.upload(
                image_bytes,
                folder="ai-pricing-agent",
                resource_type="image",
            )

            cloudinary_url = upload_result.get(
                "secure_url"
            )

            print(
                "CLOUDINARY:",
                cloudinary_url
            )

            # =============================================
            # GOOGLE VISION
            # =============================================

            detected_query = await vision.detect_query(
                image_bytes
            )

            print(
                "VISION QUERY:",
                detected_query
            )

            final_query = detected_query

        except Exception as e:

            print("IMAGE ANALYSIS FAILED:", e)

    # =====================================================
    # NO QUERY FOUND
    # =====================================================

    if not final_query:

        return {
            "success": False,
            "error": "No query detected"
        }

    # =====================================================
    # SEARCH
    # =====================================================

    result = await engine.analyze(final_query)

    return result