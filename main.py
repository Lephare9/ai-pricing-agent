import os
import logging
import re
import requests
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# =========================
# SAFE IMPORT
# =========================
try:
    import google.generativeai as genai
except:
    raise RuntimeError("google-generativeai mangler i requirements.txt")

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-pricing-agent")

logger.info("🔥 AI PRICING AGENT v4 START")

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
    allow_origins=["*"],  # sæt din Netlify URL senere
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"status": "ok", "version": "v4"}

# =========================
# GEMINI (DANSK + STAND)
# =========================
def detect_object(image_bytes: bytes, mime_type: str):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")

        response = model.generate_content([
            {
                "mime_type": mime_type,
                "data": image_bytes
            },
            "Beskriv objektet kort på dansk (1-3 ord) OG vurder stand (fx 'god stand', 'slidt'). Format: 'objekt, stand'"
        ])

        text = (response.text or "").strip().lower()

        logger.info(f"🧠 GEMINI RAW: {text}")

        if "," in text:
            title, condition = text.split(",", 1)
            return title.strip(), condition.strip()

        return text, "ukendt stand"

    except Exception as e:
        logger.error(f"🚨 GEMINI ERROR: {str(e)}")
        return "genstand", "ukendt stand"

# =========================
# PRICE PARSER
# =========================
def parse_price(raw):
    if not raw:
        return None

    raw = raw.replace(",", ".")
    matches = re.findall(r"\d+\.?\d*", raw)

    if not matches:
        return None

    try:
        return int(float(matches[0]))
    except:
        return None

# =========================
# SERPAPI (SHOPPING)
# =========================
def get_shopping_prices(query):
    try:
        params = {
            "engine": "google_shopping",
            "q": query,
            "api_key": SERPAPI_KEY,
            "hl": "da",
            "gl": "dk"
        }

        r = requests.get("https://serpapi.com/search", params=params, timeout=10)

        if r.status_code != 200:
            logger.error(f"SERPAPI shopping HTTP {r.status_code}")
            return []

        data = r.json()
        prices = []

        for item in data.get("shopping_results", []):
            p = parse_price(item.get("price"))
            if p:
                prices.append(p)

        return prices

    except Exception as e:
        logger.error(f"🚨 SHOPPING ERROR: {str(e)}")
        return []

# =========================
# SERPAPI (ORGANIC)
# =========================
def get_organic_prices(query):
    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": SERPAPI_KEY,
            "hl": "da",
            "gl": "dk"
        }

        r = requests.get("https://serpapi.com/search", params=params, timeout=10)

        if r.status_code != 200:
            logger.error(f"SERPAPI organic HTTP {r.status_code}")
            return []

        data = r.json()
        prices = []

        for item in data.get("organic_results", []):
            snippet = item.get("snippet", "")
            matches = re.findall(r"\d{2,5}", snippet)

            for m in matches:
                try:
                    prices.append(int(m))
                except:
                    pass

        return prices

    except Exception as e:
        logger.error(f"🚨 ORGANIC ERROR: {str(e)}")
        return []

# =========================
# PRICE ENGINE (ROBUST)
# =========================
def calculate_price(prices):
    if not prices:
        return 0

    # filtrer åbenlyst skrald
    prices = [p for p in prices if 20 < p < 20000]

    if not prices:
        return 0

    prices.sort()
    n = len(prices)

    # trim top/bund 20%
    if n >= 10:
        cut = int(n * 0.2)
        prices = prices[cut:-cut]

    if not prices:
        return 0

    # median
    mid = len(prices) // 2

    if len(prices) % 2 == 0:
        return (prices[mid - 1] + prices[mid]) // 2
    else:
        return prices[mid]

# =========================
# ANALYZE
# =========================
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    logger.info("=== /analyze ===")

    try:
        image_bytes = await file.read()

        if not image_bytes:
            return {
                "title": "Ingen fil",
                "condition": "",
                "price": 0,
                "results": []
            }

        logger.info(f"📷 SIZE: {len(image_bytes)}")
        logger.info(f"📷 MIME: {file.content_type}")

        # =========================
        # GEMINI
        # =========================
        title, condition = detect_object(image_bytes, file.content_type)

        logger.info(f"🧠 TITLE: {title}")
        logger.info(f"🧠 CONDITION: {condition}")

        # =========================
        # SERPAPI
        # =========================
        query = f"{title} brugt pris danmark"

        shopping = get_shopping_prices(query)
        organic = get_organic_prices(query)

        all_prices = shopping + organic

        logger.info(f"💰 SHOPPING: {shopping}")
        logger.info(f"💰 ORGANIC: {organic}")
        logger.info(f"💰 ALL: {all_prices}")

        final_price = calculate_price(all_prices)

        logger.info(f"💰 FINAL PRICE: {final_price}")

        # =========================
        # RESPONSE
        # =========================
        return {
            "title": title,
            "condition": condition,
            "price": final_price,
            "results": all_prices
        }

    except Exception as e:
        logger.error(f"🔥 CRASH: {str(e)}")

        return {
            "title": "Server fejl",
            "condition": "",
            "price": 0,
            "results": []
        }