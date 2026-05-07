import os
import logging
import re
import requests
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

try:
    import google.generativeai as genai
except:
    raise RuntimeError("google-generativeai mangler")

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-pricing-agent")

# =========================
# ENV
# =========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY mangler")

if not SERPAPI_KEY:
    raise RuntimeError("SERPAPI_KEY mangler")

genai.configure(api_key=GEMINI_API_KEY)

# =========================
# APP
# =========================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok"}

# =========================
# GEMINI
# =========================
def detect_object(image_bytes, mime):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")

        res = model.generate_content([
            {"mime_type": mime, "data": image_bytes},
            "Beskriv objektet kort på dansk (1-3 ord) OG vurder stand. Format: 'objekt, stand'"
        ])

        text = (res.text or "").strip().lower()
        logger.info(f"GEMINI RAW: {text}")

        if "," in text:
            title, condition = text.split(",", 1)
            return title.strip(), condition.strip()

        return text, "ukendt stand"

    except Exception as e:
        logger.error(f"GEMINI ERROR: {e}")
        return "genstand", "ukendt stand"

# =========================
# SERPAPI DBA SEARCH
# =========================
def get_prices(title):
    url = "https://serpapi.com/search"

    # 🔥 FORCE DBA
    query = f'site:dba.dk "{title}" kr'

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk"
    }

    for attempt in range(2):
        try:
            logger.info(f"SERP DBA attempt {attempt+1}")

            r = requests.get(url, params=params, timeout=3)

            if r.status_code != 200:
                continue

            data = r.json()

            prices = []

            for item in data.get("organic_results", []):
                snippet = item.get("snippet", "").lower()

                if "kr" not in snippet:
                    continue

                matches = re.findall(r"\d{2,5}", snippet)

                for m in matches:
                    try:
                        prices.append(int(m))
                    except:
                        pass

            if prices:
                return prices

        except Exception as e:
            logger.warning(f"SERP ERROR {attempt+1}: {e}")

    return []

# =========================
# PRICE ENGINE
# =========================
def calculate_price(prices):
    logger.info(f"RAW PRICES: {prices}")

    if not prices:
        return 0

    # kun realistiske priser
    prices = [p for p in prices if 45 < p < 5000]

    logger.info(f"FILTERED: {prices}")

    if not prices:
        return 0

    prices.sort()

    mid = len(prices) // 2

    if len(prices) % 2 == 0:
        result = (prices[mid - 1] + prices[mid]) // 2
    else:
        result = prices[mid]

    logger.info(f"FINAL PRICE: {result}")

    return result

# =========================
# ANALYZE
# =========================
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        image = await file.read()

        title, condition = detect_object(image, file.content_type)

        prices = get_prices(title)

        final_price = calculate_price(prices)

        return {
            "title": title,
            "condition": condition,
            "price": final_price,
            "results": prices
        }

    except Exception as e:
        logger.error(f"CRASH: {e}")
        return {
            "title": "Fejl",
            "condition": "",
            "price": 0,
            "results": []
        }