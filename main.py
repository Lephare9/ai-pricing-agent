from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re, time
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ---------- GEMINI ----------
def call_gemini(prompt, image=None):

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    parts = [{"text": prompt}]
    if image:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image
            }
        })

    payload = {"contents": [{"parts": parts}]}

    try:
        r = requests.post(url, json=payload, timeout=15)
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return None


def extract_json(text):
    try:
        return json.loads(text[text.find("{"):text.rfind("}")+1])
    except:
        return {}


# ---------- IDENTIFY + CATEGORY ----------
def identify(image):

    prompt = """
Identificér produkt + kategori.

Returnér JSON:
{
 "name": "",
 "brand": "",
 "condition": "",
 "category": ""
}

Kategorier:
furniture, decor, clothing_branded, clothing_generic,
small_item, book, art, vehicle, electronics
"""

    raw = call_gemini(prompt, image)

    try:
        return extract_json(raw)
    except:
        return {}


# ---------- DBA SEARCH ----------
def search_dba(query):

    url = f"https://www.dba.dk/soeg/?soeg={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        text = soup.get_text(" ")

        matches = re.findall(r"(\d{2,5})[\s.,-]*kr", text.lower())
        prices = [int(m) for m in matches if 20 < int(m) < 50000]

        return prices[:15]

    except:
        return []


# ---------- CALC ----------
def round5(x):
    return int(round(x / 5) * 5)


def calc_range(prices):

    if not prices:
        return None

    prices = sorted(prices)

    if len(prices) > 5:
        cut = max(1, int(len(prices) * 0.2))
        prices = prices[cut:-cut]

    avg = sum(prices) / len(prices)

    return round5(avg * 0.9), round5(avg * 1.1)


# ---------- CATEGORY ROUTING ----------
def handle_category(data):

    name = data.get("name", "")
    brand = data.get("brand", "")
    category = data.get("category", "")
    condition = data.get("condition", "")

    query = f"{brand} {name}".strip()

    # 🔴 BLOCKED
    if category in ["vehicle", "electronics"]:
        return {
            "description": f"{name}\n{brand}",
            "price_range": "Ikke understøttet",
            "condition": condition,
            "note": "special kategori"
        }

    # 👕 TØJ (generic)
    if category == "clothing_generic":
        return {
            "description": f"{name}\n{brand}",
            "price_range": "50 - 150 kr",
            "condition": condition,
            "note": "standard tøj"
        }

    # 👕 TØJ (brand)
    if category == "clothing_branded":
        prices = search_dba(query)
        result = calc_range(prices)

        if result:
            return {
                "description": f"{name}\n{brand}",
                "price_range": f"{result[0]} - {result[1]} kr",
                "condition": condition,
                "note": ""
            }

        return {
            "description": f"{name}\n{brand}",
            "price_range": "100 - 300 kr",
            "condition": condition,
            "note": "lignende"
        }

    # 📚 BØGER
    if category == "book":
        return {
            "description": f"{name}",
            "price_range": "10 - 100 kr",
            "condition": condition,
            "note": ""
        }

    # 🧸 SMALL ITEM
    if category == "small_item":
        prices = search_dba(query)

        prices = [p for p in prices if p < 500]

        result = calc_range(prices)

        if result:
            return {
                "description": f"{name}",
                "price_range": f"{result[0]} - {result[1]} kr",
                "condition": condition,
                "note": ""
            }

        return {
            "description": f"{name}",
            "price_range": "20 - 300 kr",
            "condition": condition,
            "note": "lignende"
        }

    # 🪑 FURNITURE / DECOR / ART (CORE)
    prices = search_dba(query)

    result = calc_range(prices)

    if result:
        return {
            "description": f"{name}\n{brand}",
            "price_range": f"{result[0]} - {result[1]} kr",
            "condition": condition,
            "note": ""
        }

    # fallback lignende
    prices = search_dba(name + " brugt")

    result = calc_range(prices)

    if result:
        return {
            "description": f"{name}\n{brand}",
            "price_range": f"{result[0]} - {result[1]} kr",
            "condition": condition,
            "note": "lignende"
        }

    return {
        "description": f"{name}\n{brand}",
        "price_range": "100 - 500 kr",
        "condition": condition,
        "note": "lignende"
    }


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()
    img64 = base64.b64encode(img).decode()

    data = identify(img64)

    if not data:
        return {
            "description": "Ukendt produkt",
            "price_range": "Ingen pris",
            "condition": "",
            "note": ""
        }

    return handle_category(data)


@app.get("/")
def root():
    return {"status": "ok", "mode": "v12-category-engine"}