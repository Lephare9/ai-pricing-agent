from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google import genai
import base64
import os
import re
import statistics
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

PRICE_REGEX = r"(\\d{2,6})\\s?(kr|dkk)?"

# ----------------------------------------
# Gemini analyse
# ----------------------------------------

async def analyze_image(image_bytes):

    image_b64 = base64.b64encode(image_bytes).decode()

    prompt = """
Du er ekspert i danske brugtmøbler.

Svar KUN som JSON.

Find:
- titel
- kategori
- alternative søgninger

Regler:
- ALT skal være dansk
- ingen engelske ord
- korte præcise søgninger
- fokus på DBA/Facebook Marketplace

Format:

{
  "titel": "...",
  "kategori": "...",
  "queries": [
    "...",
    "...",
    "..."
  ]
}
"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
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


# ----------------------------------------
# Pris søgning
# ----------------------------------------

async def serp_search(query):

    url = "https://serpapi.com/search.json"

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "google_domain": "google.dk"
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params=params)

    return response.json()


# ----------------------------------------
# Pris parser
# ----------------------------------------

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


# ----------------------------------------
# Analyze endpoint
# ----------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        # Gemini vision
        raw = await analyze_image(image_bytes)

        print("RAW GEMINI:", raw)

        clean = raw.replace("```json", "").replace("```", "").strip()

        import json
        vision = json.loads(clean)

        title = vision["titel"]
        category = vision["kategori"]
        queries = vision["queries"]

        print("QUERIES:", queries)

        # Parallel søgninger
        tasks = []

        for q in queries:
            search_query = f"{q} brugt dba facebook marketplace"
            tasks.append(serp_search(search_query))

        results = await __import__("asyncio").gather(*tasks)

        prices = []

        for result in results:
            prices.extend(extract_prices(result))

        prices = list(set(prices))

        print("PRICES:", prices)

        if prices:
            median_price = int(statistics.median(prices))
        else:
            median_price = None

        return {
            "success": True,
            "titel": title,
            "kategori": category,
            "medianpris": median_price,
            "fundne_priser": prices[:20]
        }

    except Exception as e:

        print("ERROR:", str(e))

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )