from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
import io
import re
import json
import base64
import requests

from statistics import median
from PIL import Image
from openai import OpenAI

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


def clean_text(text):
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    return text


def resize_image(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))

    max_size = 1200

    if image.width > max_size or image.height > max_size:
        image.thumbnail((max_size, max_size))

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)

    return output.getvalue()


def detect_item(image_bytes):

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """
Du analyserer brugte ting fra DBA/loppemarked.

Returnér KUN gyldig JSON.

Regler:
- title = kort dansk produkttitel
- designer = designer/navn hvis kendt
- material = primært materiale
- condition = kort dansk stand

Eksempel:
{
  "title":"Kubus lysestage",
  "designer":"Mogens Lassen",
  "material":"metal",
  "condition":"god stand"
}
"""
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyser dette billede"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        max_tokens=200
    )

    text = response.choices[0].message.content.strip()

    try:
        data = json.loads(text)

        return {
            "title": clean_text(data.get("title", "Ukendt")),
            "designer": clean_text(data.get("designer", "")),
            "material": clean_text(data.get("material", "")),
            "condition": clean_text(data.get("condition", "Brugt"))
        }

    except Exception:
        return {
            "title": "Ukendt",
            "designer": "",
            "material": "",
            "condition": "Brugt"
        }


def build_query(vision):

    parts = []

    if vision["designer"]:
        parts.append(vision["designer"])

    if vision["title"]:
        parts.append(vision["title"])

    if vision["material"]:
        parts.append(vision["material"])

    parts.append("brugt")

    query = " ".join(parts)

    query = re.sub(r"\s+", " ", query)

    return query.strip()


def extract_prices(data):

    prices = []

    organic = data.get("organic_results", [])

    for item in organic:

        text = f"""
        {item.get('title', '')}
        {item.get('snippet', '')}
        """

        matches = re.findall(r"(\d{2,5})\s*kr", text.lower())

        for match in matches:
            try:
                price = int(match)

                if 20 <= price <= 50000:
                    prices.append(price)

            except:
                pass

    return prices


def filter_prices(prices):

    if not prices:
        return []

    prices = sorted(prices)

    q1 = prices[len(prices) // 4]
    q3 = prices[(len(prices) * 3) // 4]

    iqr = q3 - q1

    low = q1 - (1.5 * iqr)
    high = q3 + (1.5 * iqr)

    filtered = [
        p for p in prices
        if low <= p <= high
    ]

    if not filtered:
        filtered = prices

    return filtered


def search_prices(query):

    if not SERPAPI_KEY:
        return []

    try:

        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_KEY,
                "hl": "da",
                "gl": "dk",
                "num": 10
            },
            timeout=12
        )

        data = response.json()

        raw_prices = extract_prices(data)

        filtered = filter_prices(raw_prices)

        print("QUERY:", query)
        print("RAW:", raw_prices)
        print("FILTERED:", filtered)

        return filtered

    except Exception as e:

        print("SERP ERROR:", str(e))

        return []


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        image_bytes = resize_image(image_bytes)

        vision = detect_item(image_bytes)

        print("VISION:", vision)

        query = build_query(vision)

        prices = search_prices(query)

        if prices:

            median_price = int(median(prices))

            low = min(prices)
            high = max(prices)

            if low != high:
                price_text = f"{low} – {high} kr"
            else:
                price_text = f"{median_price} kr"

        else:

            median_price = None
            price_text = "Ukendt pris"

        return JSONResponse({
            "title": vision["title"],
            "designer": vision["designer"],
            "material": vision["material"],
            "condition": vision["condition"],

            "price": price_text,

            "found_prices": len(prices),

            "prices": prices
        })

    except Exception as e:

        print("SERVER ERROR:", str(e))

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )