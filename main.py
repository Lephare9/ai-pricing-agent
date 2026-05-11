# main.py

import os
import re
import json

import httpx
import cloudinary
import cloudinary.uploader

import google.generativeai as genai

from bs4 import BeautifulSoup

from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware


# =========================================================
# CONFIG
# =========================================================

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

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

async def detect_with_google_vision(image_url: str):

    endpoint = (
        "https://vision.googleapis.com/v1/images:annotate"
        f"?key={GOOGLE_VISION_API_KEY}"
    )

    body = {
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
                    },
                    {
                        "type": "WEB_DETECTION",
                        "maxResults": 10
                    },
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as client:

        response = await client.post(
            endpoint,
            json=body
        )

    data = response.json()

    return data


# =========================================================
# GEMINI
# =========================================================

async def detect_with_gemini(image_url: str):

    model = genai.GenerativeModel(
        "gemini-1.5-flash"
    )

    prompt = f"""
    Du analyserer billeder af designobjekter.

    Returnér KUN JSON.

    Format:

    {{
      "object_type": "",
      "designer": "",
      "brand": "",
      "search_query": "",
      "danish_keywords": []
    }}

    Vigtigt:

    - Brug danske ord
    - search_query skal være kort
    - Gæt kun hvis sikker
    - Hvis ukendt:
      designer=""
      brand=""
    - Fokusér på:
      stole
      lamper
      borde
      møbler
      designobjekter
    - Ignorér:
      gulv
      plywood
      texture
      steel
      varnish
    - Returnér kun JSON
    """

    response = model.generate_content([
        prompt,
        image_url
    ])

    text = response.text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")
    text = text.strip()

    try:
        return json.loads(text)
    except:
        return {
            "object_type": "",
            "designer": "",
            "brand": "",
            "search_query": "",
            "danish_keywords": []
        }


# =========================================================
# SEARCH BUILDER
# =========================================================

def build_search_query(vision_data, gemini_data):

    web_entities = (
        vision_data["responses"][0]
        .get("webDetection", {})
        .get("webEntities", [])
    )

    labels = (
        vision_data["responses"][0]
        .get("labelAnnotations", [])
    )

    candidates = []

    # GEMINI FIRST

    search_query = (
        gemini_data.get("search_query") or ""
    ).strip()

    if search_query:
        candidates.append(search_query)

    designer = (
        gemini_data.get("designer") or ""
    ).strip()

    brand = (
        gemini_data.get("brand") or ""
    ).strip()

    object_type = (
        gemini_data.get("object_type") or ""
    ).strip()

    if designer and object_type:
        candidates.append(
            f"{designer} {object_type}"
        )

    if brand and object_type:
        candidates.append(
            f"{brand} {object_type}"
        )

    # WEB ENTITIES

    for entity in web_entities:

        desc = (
            entity.get("description") or ""
        ).lower()

        score = entity.get("score", 0)

        if score < 1:
            continue

        if len(desc) < 3:
            continue

        candidates.append(desc)

    # LABEL FALLBACK

    allowed_labels = [
        "chair",
        "lamp",
        "table",
        "furniture",
        "sofa",
        "stool",
    ]

    label_map = {
        "chair": "stol",
        "lamp": "lampe",
        "table": "bord",
        "furniture": "møbel",
        "sofa": "sofa",
        "stool": "skammel",
    }

    for label in labels:

        desc = (
            label.get("description") or ""
        ).lower()

        if desc in allowed_labels:

            candidates.append(
                label_map.get(desc, desc)
            )

    # CLEANUP

    cleaned = []

    for item in candidates:

        item = item.strip().lower()

        if len(item) < 3:
            continue

        if item not in cleaned:
            cleaned.append(item)

    if not cleaned:
        return "design"

    return cleaned[0]


# =========================================================
# DBA
# =========================================================

class DBAScraper:

    async def search(self, query: str):

        url = (
            f"https://www.dba.dk/soeg/?soeg={query}"
        )

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
# ENGINE
# =========================================================

class PricingEngine:

    def __init__(self):

        self.dba = DBAScraper()
        self.lauritz = LauritzScraper()

    async def analyze(self, image_url: str):

        vision_data = await detect_with_google_vision(
            image_url
        )

        gemini_data = await detect_with_gemini(
            image_url
        )

        query = build_search_query(
            vision_data,
            gemini_data
        )

        print("SEARCH QUERY:", query)

        all_results = []

        dba_results = await self.dba.search(query)

        print("DBA:", len(dba_results))

        all_results.extend(dba_results)

        lauritz_results = await self.lauritz.search(query)

        print("Lauritz:", len(lauritz_results))

        all_results.extend(lauritz_results)

        all_results = [
            item for item in all_results
            if item.get("title")
        ]

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