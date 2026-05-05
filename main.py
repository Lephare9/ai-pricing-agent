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


# ---------- PARSE ----------
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return {}


# ---------- IDENTIFY ----------
def identify_object(image_base64):

    prompt = """
Identificér produkt meget præcist.

Returnér KUN JSON:

{
  "name": "",
  "brand": "",
  "type": ""
}

Regler:
- inkluder model hvis muligt
- hvis ukendt brand → skriv ""
- vær kort og konkret
"""

    return call_gemini(prompt, image_base64)


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

            found = re.findall(r"(\d{2,5})\s?kr", text)

            for p in found:
                val = int(p)
                if 20 < val < 50000:
                    prices.append(val)

        return prices[:20]

    except Exception as e:
        print("SEARCH ERROR:", e)
        return []


# ---------- CLEAN ----------
def clean_prices(prices):

    if len(prices) < 5:
        return prices

    prices.sort()

    cut = max(1, int(len(prices) * 0.2))

    return prices[cut:-cut]


# ---------- ROUND ----------
def round5(x):
    return int(round(x / 5) * 5)


# ---------- CALC ----------
def compute_range(prices):

    if len(prices) < 3:
        return 100, 300, 50

    prices = clean_prices(prices)

    avg = sum(prices) / len(prices)

    spread = 0.10

    min_p = round5(avg * (1 - spread))
    max_p = round5(avg * (1 + spread))

    return min_p, max_p, 90


# ---------- AI FALLBACK ----------
def fallback_ai(name, brand):

    prompt = f"""
Find 8 realistiske brugtpriser i Danmark.

Produkt: {name}
Brand: {brand}

Returnér JSON:
{{
 "prices": [100,200,300]
}}
"""

    raw = call_gemini(prompt)
    data = extract_json(raw) if raw else {}

    return data.get("prices", [])


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    image_bytes = await file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # STEP 1 IDENTIFY
    identity_raw = identify_object(base64_image)
    identity = extract_json(identity_raw) if identity_raw else {}

    name = identity.get("name") or "Ukendt produkt"
    brand = identity.get("brand") or ""

    # STEP 2 QUERY (🔥 vigtig!)
    if brand:
        query = f"{brand} {name} brugt til salg dba danmark"
    else:
        query = f"{name} brugt til salg danmark"

    # STEP 3 SEARCH
    prices = search_prices(query)

    # STEP 4 FALLBACK
    if len(prices) < 3:
        prices = fallback_ai(name, brand)

    # STEP 5 CALC
    price_min, price_max, confidence = compute_range(prices)

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{price_min} - {price_max} kr",
        "confidence": confidence
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v8.1-extreme"}