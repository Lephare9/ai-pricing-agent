from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re, time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")


# ---------- GEMINI ----------
def call_gemini(prompt, image_base64=None):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    parts = [{"text": prompt}]
    if image_base64:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_base64
            }
        })

    payload = {"contents": [{"parts": parts}]}

    for _ in range(3):
        try:
            res = requests.post(url, json=payload, timeout=15)
            data = res.json()

            if "candidates" not in data:
                print("GEMINI ERROR:", data)
                time.sleep(1)
                continue

            return data["candidates"][0]["content"]["parts"][0]["text"]

        except Exception as e:
            print("ERROR:", e)
            time.sleep(1)

    return None


def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return {}


# ---------- IDENTIFY ----------
def identify(image_base64):

    prompt = """
Identificér produkt og stand.

Returnér KUN JSON:

{
  "name": "",
  "brand": "",
  "condition": ""
}
"""

    raw = call_gemini(prompt, image_base64)
    return extract_json(raw) if raw else {}


# ---------- SEARCH ----------
def search_prices(query):

    url = "https://serpapi.com/search"

    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "da",
        "gl": "dk"
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        prices = []

        for r in data.get("organic_results", []):
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()

            # fanger flere formater
            matches = re.findall(r"(\d{2,5})[\s.,-]*kr|kr[\s]*(\d{2,5})", text)

            for m in matches:
                val = int(m[0] or m[1])

                if 20 < val < 50000:
                    prices.append(val)

        print("RAW PRICES:", prices)

        return prices

    except Exception as e:
        print("SEARCH ERROR:", e)
        return []


# ---------- CLEAN ----------
def clean_prices(prices):

    if len(prices) < 3:
        return prices

    prices.sort()

    # fjern ekstreme værdier (top/bund)
    cut = max(1, int(len(prices) * 0.2))

    cleaned = prices[cut:-cut] if len(prices) > 5 else prices

    print("CLEANED:", cleaned)

    return cleaned


# ---------- CALC ----------
def round5(x):
    return int(round(x / 5) * 5)


def compute(prices):

    if len(prices) < 3:
        return None  # 🔥 INGEN fallback

    avg = sum(prices) / len(prices)

    min_p = round5(avg * 0.9)
    max_p = round5(avg * 1.1)

    return min_p, max_p


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    print("MODE: CLEAN V9.2")

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # IDENTIFY
    data = identify(base64_image)

    name = data.get("name") or ""
    brand = data.get("brand") or ""
    condition = data.get("condition") or ""

    print("IDENTIFIED:", name, brand)

    if not name:
        return {
            "description": "Kunne ikke genkende produkt",
            "price_range": "Ingen pris fundet",
            "condition": ""
        }

    # QUERY
    query = f"{brand} {name} pris brugt danmark"

    print("QUERY:", query)

    # SEARCH
    prices = search_prices(query)

    prices = clean_prices(prices)

    # CALC
    result = compute(prices)

    if not result:
        return {
            "description": f"{name}\n{brand}",
            "price_range": "Ingen pris fundet",
            "condition": condition
        }

    min_p, max_p = result

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{min_p} - {max_p} kr",
        "condition": condition
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "clean-v9.2"}