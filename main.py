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


# ---------- GEMINI IDENTIFY ----------
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

    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()

        if "candidates" not in data:
            print("GEMINI ERROR:", data)
            return None

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        print("ERROR:", e)
        return None


def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return {}


def identify_object(image_base64):

    prompt = """
Identificér produkt meget præcist.

Returnér KUN JSON:

{
  "name": "",
  "brand": ""
}
"""

    return call_gemini(prompt, image_base64)


# ---------- SEARCH + SCORE ----------
def search_prices_scored(query):

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

        results = []

        for r in data.get("organic_results", []):
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()

            found = re.findall(r"(\d{2,5})\s?kr", text)

            score = 0

            if "dba" in text:
                score += 3
            if "brugt" in text:
                score += 2
            if "til salg" in text:
                score += 1
            if "nypris" in text:
                score -= 3
            if "shop" in text:
                score -= 2

            for p in found:
                val = int(p)
                if 20 < val < 50000:
                    results.append((val, score))

        return results

    except Exception as e:
        print("SEARCH ERROR:", e)
        return []


# ---------- FILTER ----------
def process_prices(results, name, brand):

    if not results:
        return []

    # behold kun relevante
    results = [r for r in results if r[1] >= 0]

    # sorter efter score
    results.sort(key=lambda x: x[1], reverse=True)

    # top hits
    results = results[:10]

    prices = [r[0] for r in results]

    # 🔥 design boost
    if any(k in (name + brand).lower() for k in ["bolia","hay","muuto","fritz","mater","wegner"]):
        prices = [p for p in prices if p > 500]

    # 🔥 fjern outliers
    if len(prices) >= 5:
        prices.sort()
        cut = int(len(prices) * 0.2)
        prices = prices[cut:-cut]

    return prices


# ---------- FINAL CALC ----------
def round5(x):
    return int(round(x / 5) * 5)


def compute_final(prices):

    if len(prices) < 3:
        return 100, 300, 50

    avg = sum(prices) / len(prices)

    min_p = round5(avg * 0.9)
    max_p = round5(avg * 1.1)

    return min_p, max_p, 95


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1: IDENTIFY
    identity_raw = identify_object(base64_image)
    identity = extract_json(identity_raw) if identity_raw else {}

    name = identity.get("name") or "produkt"
    brand = identity.get("brand") or ""

    # STEP 2: SEARCH
    query = f"{brand} {name} brugt til salg dba danmark"
    results = search_prices_scored(query)

    prices = process_prices(results, name, brand)

    # STEP 3: CALC
    price_min, price_max, confidence = compute_final(prices)

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": confidence
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v9-pro"}