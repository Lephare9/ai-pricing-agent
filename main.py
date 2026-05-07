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
    return {"status": "ok", "version": "v4"}

# =========================
# GEMINI (DANSK)
# =========================
def detect_object(image_bytes, mime):
    model = genai.GenerativeModel("gemini-2.5-flash")

    res = model.generate_content([
        {"mime_type": mime, "data": image_bytes},
        "Hvad er objektet? Svar kun 1-3 danske ord."
    ])

    text = (res.text or "").strip().lower()

    if not text or len(text) > 40:
        return "genstand"

    return text

# =========================
# PRICE PARSER (FIX)
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
        data = r.json()

        prices = []

        for item in data.get("shopping_results", []):
            p = parse_price(item.get("price"))
            if p:
                prices.append(p)

        return prices

    except Exception as e:
        logger.error(f"shopping error: {e}")
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
        logger.error(f"organic error: {e}")
        return []

# =========================
# PRICE ENGINE (v4)
# =========================
def calculate_price(prices):
    if not prices:
        return 0

    # bredere filter (vigtigt!)
    prices = [p for p in prices if 20 < p < 20000]

    if not prices:
        return 0

    prices.sort()

    n = len(prices)

    # trim 20%
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
    try:
        image = await file.read()

        title = detect_object(image, file.content_type)
        logger.info(f"OBJECT: {title}")

        query = f"{title} brugt pris danmark"

        # 🔥 to kilder
        shopping = get_shopping_prices(query)
        organic = get_organic_prices(query)

        all_prices = shopping + organic

        logger.info(f"SHOPPING: {shopping}")
        logger.info(f"ORGANIC: {organic}")

        final_price = calculate_price(all_prices)

        return {
            "title": title,
            "price": final_price,
            "results": all_prices
        }

    except Exception as e:
        logger.error(f"CRASH: {e}")
        return {
            "title": "Fejl",
            "price": 0,
            "results": []
        }