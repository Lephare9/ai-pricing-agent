from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import os, base64, requests, json, re

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


# ---------- IDENTIFY ----------
def identify(image):

    prompt = """
Du er ekspert i designmøbler og brugtmarked.

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
"""

    raw = call_gemini(prompt, image)
    print("RAW:", raw)

    data = extract_json(raw)

    if not data:
        return {"name": "stol", "brand": "", "category": "furniture"}

    if not data.get("brand") and data.get("name"):
        data["brand"] = data["name"].split()[0]

    if data.get("brand") and data.get("model"):
        data["name"] = f"{data['brand']} {data['model']}"

    return data


# ---------- BUILD QUERY ----------
def build_query(data):

    parts = []

    for key in ["brand", "name", "material", "shape", "style"]:
        if data.get(key):
            parts.append(data[key])

    parts.append("brugte priser danmark")

    query = " ".join(parts)

    print("QUERY:", query)

    return query


# ---------- GOOGLE SEARCH ----------
def google_search(query):

    url = "https://serpapi.com/search"

    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "da",
        "gl": "dk"
    }

    try:
        r = requests.get(url, params=params)
        data = r.json()

        results = []

        for res in data.get("organic_results", []):
            text = (res.get("title", "") + " " + res.get("snippet", "")).lower()

            matches = re.findall(r"(\d{2,5})[\s.,-]*kr", text)

            for m in matches:
                price = int(m)

                if 20 < price < 50000:
                    results.append(price)

        print("GOOGLE PRICES:", results[:10])

        return results

    except Exception as e:
        print("GOOGLE ERROR:", e)
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


def calc(prices):

    if len(prices) < 2:
        return None

    avg = sum(prices) / len(prices)

    return round5(avg * 0.9), round5(avg * 1.1)


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()
    img64 = base64.b64encode(img).decode()

    data = identify(img64)

    name = data.get("name", "")
    brand = data.get("brand", "")
    category = data.get("category", "")
    condition = data.get("condition", "")

    # 🔴 blokér uønskede
    if category in ["vehicle", "electronics"]:
        return {
            "description": f"{name}\n{brand}",
            "price_range": "Ikke understøttet",
            "condition": condition,
            "note": ""
        }

    # 🔧 bygg query
    query = build_query(data)

    # 🔍 hent data
    prices = google_search(query)

    # 🔥 fallback query hvis tom
    if not prices:
        print("FALLBACK QUERY")
        prices = google_search(name + " pris brugt danmark")

    prices = smart_filter(prices, brand)

    result = calc(prices)

    # 🔥 sidste fallback
    if not result:
        if brand:
            result = (1500, 3500)
        else:
            result = (100, 500)

    min_p, max_p = result

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{min_p} - {max_p} kr",
        "condition": condition,
        "note": ""
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v15-google"}