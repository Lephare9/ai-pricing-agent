import os
import logging
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests

# =========================
# SAFE IMPORT
# =========================
try:
    import google.generativeai as genai
except Exception:
    raise RuntimeError("google-generativeai mangler i requirements.txt")

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-pricing-agent")

logger.info("🔥 AI PRICING AGENT v3 START")

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
    return {"status": "ok", "version": "v3"}

# =========================
# GEMINI (DANSK)
# =========================
def detect_object(image_bytes: bytes, mime_type: str) -> str:
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")

        response = model.generate_content([
            {
                "mime_type": mime_type,
                "data": image_bytes
            },
            "Hvad er objektet på billedet? Svar KUN med 1-3 danske ord. Fx: 'kontorstol', 'iphone 12', 'træbord'"
        ])

        text = (response.text or "").strip().lower()

        if not text or len(text) > 40:
            logger.warning(f"⚠️ Bad Gemini output: {text}")
            return "genstand"

        return text

    except Exception as e:
        logger.error(f"🚨 GEMINI ERROR: {str(e)}")
        raise

# =========================
# SERPAPI
# =========================
def fetch_prices(query: str):
    try:
        params = {
            "engine": "google_shopping",
            "q": query,
            "api_key": SERPAPI_KEY,
            "hl": "da",  # dansk
            "gl": "dk"   # Danmark
        }

        r = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=10
        )

        if r.status_code != 200:
            logger.error(f"SERPAPI HTTP {r.status_code}")
            return []

        data = r.json()

        prices = []

        for item in data.get("shopping_results", []):
            raw = item.get("price")
            if not raw:
                continue

            digits = "".join(c for c in raw if c.isdigit())
            if digits:
                prices.append(int(digits))

        return prices

    except Exception as e:
        logger.error(f"🚨 SERPAPI ERROR: {str(e)}")
        return []

# =========================
# PRIS LOGIK (TRIM + MEDIAN)
# =========================
def calculate_price(prices):
    if not prices:
        return 0

    # fjern åbenlyst skøre priser
    prices = [p for p in prices if 50 < p < 5000]

    if not prices:
        return 0

    prices = sorted(prices)

    n = len(prices)

    # trim 20% i hver ende hvis nok data
    if n >= 10:
        cut = int(n * 0.2)
        prices = prices[cut:-cut]

    # fallback hvis vi trimmede alt væk
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
                "price": 0,
                "results": []
            }

        logger.info(f"📷 SIZE: {len(image_bytes)}")
        logger.info(f"📷 MIME: {file.content_type}")

        # =========================
        # GEMINI
        # =========================
        try:
            title = detect_object(image_bytes, file.content_type)
            logger.info(f"🧠 OBJECT: {title}")
        except Exception:
            return {
                "title": "Kunne ikke analysere",
                "price": 0,
                "results": []
            }

        # =========================
        # SERPAPI
        # =========================
        search_query = f"{title} brugt pris danmark"
        prices = fetch_prices(search_query)

        logger.info(f"💰 RAW PRICES: {prices}")

        final_price = calculate_price(prices)

        logger.info(f"💰 FINAL PRICE: {final_price}")

        # =========================
        # RESPONSE
        # =========================
        return {
            "title": title,
            "price": final_price,
            "results": prices
        }

    except Exception as e:
        logger.error(f"🔥 CRASH: {str(e)}")

        return {
            "title": "Server fejl",
            "price": 0,
            "results": []
        }