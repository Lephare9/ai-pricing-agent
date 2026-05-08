from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI

import os
import io
import re
import json
import base64
import requests
from statistics import median
from PIL import Image

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


# -----------------------------
# IMAGE -> BASE64
# -----------------------------
def image_to_base64(image_bytes):

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    max_size = 1200
    image.thumbnail((max_size, max_size))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)

    return base64.b64encode(buffer.getvalue()).decode()


# -----------------------------
# OPENAI VISION
# -----------------------------
def analyze_image_openai(base64_image):

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
Analyser objektet på billedet.

Returner KUN valid JSON:

{
"title":"",
"designer":"",
"material":"",
"condition":""
}

Regler:
- identificer objekt meget præcist
- find designer hvis muligt
- brug dansk
- korte beskrivelser
- condition skal være realistisk
- ingen forklaringer
- kun JSON
"""
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
        max_tokens=300
    )

    text = response.choices[0].message.content.strip()

    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)

        if match:
            return json.loads(match.group())

    except:
        pass

    return {
        "title": "Ukendt",
        "designer": "",
        "material": "",
        "condition": "Ukendt stand"
    }


# -----------------------------
# SERP SEARCH
# -----------------------------
def serp_prices(query):

    try:

        params = {
            "engine": "google",
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 20,
            "gl": "dk",
            "hl": "da"
        }

        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=8
        )

        data = response.json()

        prices = []

        text_blob = json.dumps(data)

        matches = re.findall(r"(\d{2,5})\s?(?:kr|dkk)", text_blob.lower())

        for m in matches:
            try:
                value = int(m)

                if 50 <= value <= 25000:
                    prices.append(value)

            except:
                pass

        print("RAW:", prices)

        prices = sorted(list(set(prices)))

        filtered = []

        if prices:

            med = median(prices)

            for p in prices:

                if p >= med * 0.45 and p <= med * 2.2:
                    filtered.append(p)

        print("FILTERED:", filtered)

        return filtered

    except Exception as e:

        print("SERP ERROR:", e)
        return []


# -----------------------------
# PRICE ENGINE
# -----------------------------
def build_price(prices):

    if not prices:
        return {
            "price": "Ukendt pris",
            "found": 0
        }

    prices = sorted(prices)

    if len(prices) == 1:

        low = prices[0]
        high = prices[0]

    else:

        low = int(prices[len(prices) // 3])
        high = int(prices[(len(prices) * 2) // 3])

    return {
        "price": f"{low} – {high} kr",
        "found": len(prices)
    }


# -----------------------------
# ANALYZE ENDPOINT
# -----------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        base64_image = image_to_base64(image_bytes)

        vision = analyze_image_openai(base64_image)

        print("VISION:", vision)

        title = vision.get("title", "Ukendt")
        designer = vision.get("designer", "")
        material = vision.get("material", "")
        condition = vision.get("condition", "God stand")

        query_parts = []

        if designer:
            query_parts.append(designer)

        if title:
            query_parts.append(title)

        if material:
            query_parts.append(material)

        query_parts.append("brugt")

        query = " ".join(query_parts)

        print("QUERY:", query)

        prices = serp_prices(query)

        result = build_price(prices)

        return JSONResponse({
            "title": title,
            "designer": designer,
            "material": material,
            "condition": condition,
            "price": result["price"],
            "found": result["found"]
        })

    except Exception as e:

        print("ERROR:", e)

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


@app.get("/")
def root():
    return {"status": "ok"}