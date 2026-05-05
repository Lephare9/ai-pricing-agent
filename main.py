from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re
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

DESIGNER_BRANDS = [
    "wegner", "hans j wegner",
    "arne jacobsen",
    "børge mogensen",
    "finn juhl",
    "verner panton",
    "hay",
    "muuto"
]


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


# ---------- IDENTIFY (VISUAL) ----------
def identify(image):

    prompt = """
Du er ekspert i designmøbler og visuel genkendelse.

Analyser billedet meget detaljeret.

Returnér KUN JSON:

{
 "name": "",
 "brand": "",
 "model": "",
 "category": "",
 "material": "",
 "shape": "",
 "style": ""
}

Kategorier:
furniture, decor, clothing_branded, clothing_generic,
small_item, book, art, vehicle, electronics
"""

    raw = call_gemini(prompt, image)
    print("RAW GEMINI:", raw)

    data = extract_json(raw)

    if not data:
        data = {}

    if not data.get("brand") and data.get("name"):
        words = data["name"].split()
        if len(words) > 1:
            data["brand"] = words[0]

    if data.get("brand") and data.get("model"):
        data["name"] = f"{data['brand']} {data['model']}"

    return data


# ---------- BUILD QUERY ----------
def build_query(data):

    parts = []

    if data.get("brand"):
        parts.append(data["brand"])

    if data.get("name"):
        parts.append(data["name"])

    if data.get("material"):
        parts.append(data["material"])

    if data.get("shape"):
        parts.append(data["shape"])

    if data.get("style"):
        parts.append(data["style"])

    parts.append("danmark brugt")

    query = " ".join(parts)

    print("QUERY:", query)

    return query


# ---------- SEARCH ----------
def search_dba(query, name, brand):

    url = f"https://www.dba.dk/soeg/?soeg={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        results = []

        for item in soup.find_all("a"):

            text = item.get_text(" ").lower()

            match = re.search(r"(\d{2,5})[\s.,-]*kr", text)
            if not match:
                continue

            price = int(match.group(1))
            if not (50 < price < 50000):
                continue

            score = 0

            if brand and brand.lower() in text:
                score += 4

            for word in name.lower().split():
                if word in text:
                    score += 1

            results.append({
                "price": price,
                "score": score
            })

        results.sort(key=lambda x: x["score"], reverse=True)

        prices = [r["price"] for r in results]

        return prices[:15]

    except:
        return []


# ---------- FILTER ----------
def smart_filter(prices, brand):

    if not prices:
        return []

    prices = sorted(prices)
    median = prices[len(prices)//2]

    filtered = []

    for p in prices:
        if p < median * 0.4:
            continue
        if p > median * 2.5:
            continue
        filtered.append(p)

    if brand:
        filtered = [p for p in filtered if p > median * 0.6]

    return filtered


# ---------- CALC ----------
def round5(x):
    return int(round(x / 5) * 5)


def calc_range(prices):

    if len(prices) < 2:
        return None

    avg = sum(prices) / len(prices)

    return round5(avg * 0.9), round5(avg * 1.1)


# ---------- CATEGORY ----------
def handle_category(data):

    name = data.get("name", "")
    brand = data.get("brand", "")
    category = data.get("category", "")
    condition = data.get("condition", "")

    if category in ["vehicle", "electronics"]:
        return {
            "description": f"{name}\n{brand}",
            "price_range": "Ikke understøttet",
            "condition": condition,
            "note": "special kategori"
        }

    if category == "clothing_generic":
        return {
            "description": name,
            "price_range": "50 - 150 kr",
            "condition": condition,
            "note": ""
        }

    if category == "book":
        return {
            "description": name,
            "price_range": "10 - 100 kr",
            "condition": condition,
            "note": ""
        }

    if category == "small_item":
        prices = search_dba(name, name, brand)
        prices = [p for p in prices if p < 500]
        prices = smart_filter(prices, brand)

        result = calc_range(prices)

        if result:
            return {
                "description": name,
                "price_range": f"{result[0]} - {result[1]} kr",
                "condition": condition,
                "note": ""
            }

        return {
            "description": name,
            "price_range": "20 - 300 kr",
            "condition": condition,
            "note": "lignende"
        }

    # 🔥 CORE (visual search)
    query = build_query(data)

    prices = search_dba(query, name, brand)
    prices = smart_filter(prices, brand)

    # designer boost
    if brand and brand.lower() in DESIGNER_BRANDS:
        prices = [p for p in prices if p > 800]

    result = calc_range(prices)

    if result:
        return {
            "description": f"{name}\n{brand}",
            "price_range": f"{result[0]} - {result[1]} kr",
            "condition": condition,
            "note": ""
        }

    # fallback
    prices = search_dba(name, name, "")
    prices = smart_filter(prices, "")

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
    return {"status": "ok", "mode": "v14-visual"}