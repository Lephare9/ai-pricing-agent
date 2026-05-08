from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from google import genai

import base64
import os
import re
import json
import asyncio
import statistics
import traceback
import httpx

# ---------------------------------------------------
# APP
# ---------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# ENV
# ---------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

print("GEMINI:", bool(GEMINI_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))

# ---------------------------------------------------
# GEMINI CLIENT
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# PRICE REGEX
# ---------------------------------------------------

PRICE_REGEX = r"(\d{2,6})\s?(kr|dkk)?"

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok"}

# ---------------------------------------------------
# GEMINI IMAGE ANALYSIS
# ---------------------------------------------------

async def analyze_image(image_bytes):

    image_b64 = base64.b64encode(image_bytes).decode()

    prompt = """
Du er ekspert i danske brugtmøbler.

Analyser billedet.

Svar KUN som valid JSON.

Regler:
- ALT skal være dansk
- ingen engelske ord
- korte søgninger
- fokus på DBA og Facebook Marketplace
- beskriv typen af møbel korrekt

Format:

{
  "titel": "kort dansk titel",
  "kategori": "møbelkategori",
  "queries": [
    "søgning 1",
    "søgning 2",
    "søgning 3"
  ]
}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_b64
                        }
                    }
                ]
            }
        ]
    )

    return response.text

# ---------------------------------------------------
# SERPAPI SEARCH
# ---------------------------------------------------

async def serp_search(query):

    print("SEARCH:", query)

    url = "https://serpapi.com/search.json"

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "google_domain": "google.dk"
    }

    async with httpx.AsyncClient(timeout=20) as client:

        response = await client.get(
            url,
            params=params
        )

    data = response.json()

    return data

# ---------------------------------------------------
# EXTRACT PRICES
# ---------------------------------------------------

def extract_prices(data):

    text = str(data).lower()

    matches = re.findall(PRICE_REGEX, text)

    prices = []

    for match in matches:

        try:

            price = int(match[0])

            if 50 <= price <= 100000:
                prices.append(price)

        except:
            pass

    return prices

# ---------------------------------------------------
# ANALYZE ENDPOINT
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        print("===================================")
        print("START ANALYZE")
        print("===================================")

        image_bytes = await file.read()

        print("IMAGE SIZE:", len(image_bytes))

        # ---------------------------------------
        # GEMINI
        # ---------------------------------------

        raw = await analyze_image(image_bytes)

        print("RAW GEMINI RESPONSE:")
        print(raw)

        clean = (
            raw
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        print("CLEANED RESPONSE:")
        print(clean)

        # ---------------------------------------
        # PARSE JSON
        # ---------------------------------------

        vision = json.loads(clean)

        print("PARSED JSON:")
        print(vision)

        title = vision.get("titel", "Ukendt")
        category = vision.get("kategori", "Ukendt")
        queries = vision.get("queries", [])

        print("TITLE:", title)
        print("CATEGORY:", category)
        print("QUERIES:", queries)

        # ---------------------------------------
        # SEARCHES
        # ---------------------------------------

        tasks = []

        for q in queries:

            search_query = f"{q} brugt dba facebook marketplace"

            tasks.append(
                serp_search(search_query)
            )

        results = await asyncio.gather(*tasks)

        print("SEARCH RESULTS:", len(results))

        # ---------------------------------------
        # PRICE EXTRACTION
        # ---------------------------------------

        prices = []

        for result in results:

            found_prices = extract_prices(result)

            print("FOUND:", found_prices[:20])

            prices.extend(found_prices)

        prices = list(set(prices))

        print("ALL PRICES:", prices)

        # ---------------------------------------
        # MEDIAN
        # ---------------------------------------

        if prices:
            median_price = int(statistics.median(prices))
        else:
            median_price = None

        print("MEDIAN:", median_price)

        # ---------------------------------------
        # RESPONSE
        # ---------------------------------------

        return {
            "success": True,
            "titel": title,
            "kategori": category,
            "medianpris": median_price,
            "fundne_priser": prices[:20]
        }

    except Exception as e:

        print("===================================")
        print("FULL ERROR")
        print("===================================")

        print(str(e))

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )