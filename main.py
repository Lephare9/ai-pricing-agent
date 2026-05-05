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

    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            data = r.json()

            if "candidates" not in data:
                time.sleep(1)
                continue

            return data["candidates"][0]["content"]["parts"][0]["text"]

        except:
            time.sleep(1)

    return None


def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "")
        return json.loads(text[text.find("{"):text.rfind("}")+1])
    except:
        return {}


# ---------- PRICELESS ----------
def check_priceless(image):

    prompt = """
Er dette primært:
- et menneske
- et ansigt
- eller et dyr

OG ikke et produkt?

Svar KUN:
YES eller NO
"""

    res = call_gemini(prompt, image)
    return "YES" in (res or "").upper()


# ---------- IDENTIFY ----------
def identify(image):

    prompt = """
Identificér produkt præcist.

- brug brand hvis muligt
- brug model hvis muligt

Returnér JSON:
{
 "name": "",
 "brand": "",
 "condition": ""
}
"""

    raw = call_gemini(prompt, image)
    return extract_json(raw) if raw else {}


# ---------- SEARCH ----------
def search(query):

    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "da",
        "gl": "dk"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        results = []

        for res in data.get("organic_results", []):
            text = res.get("title", "") + " " + res.get("snippet", "")

            matches = re.findall(r"(\d{2,5})\s*kr", text.lower())

            for m in matches:
                price = int(m)

                if 20 < price < 50000:
                    results.append({
                        "text": text,
                        "price": price
                    })

        return results

    except:
        return []


# ---------- AI FILTER ----------
def filter_prices(name, results):

    if not results:
        return []

    prompt = f"""
Produkt: {name}

Data:
{results}

OPGAVE:
- behold priser der KAN være samme type
- fjern kun helt forkerte

Returnér:
[100,200,300]
"""

    raw = call_gemini(prompt)

    try:
        return json.loads(raw)
    except:
        return []


# ---------- CALC ----------
def round5(x):
    return int(round(x / 5) * 5)


def calculate(filtered, raw):

    # LEVEL 1 (AI filtreret)
    if len(filtered) >= 3:
        prices = sorted(filtered)

        cut = max(1, int(len(prices) * 0.2))
        prices = prices[cut:-cut] if len(prices) > 5 else prices

        avg = sum(prices) / len(prices)
        return round5(avg * 0.9), round5(avg * 1.1)

    # LEVEL 2 (raw)
    raw_prices = [r["price"] for r in raw]

    if len(raw_prices) >= 3:
        prices = sorted(raw_prices)

        cut = max(1, int(len(prices) * 0.3))
        prices = prices[cut:-cut] if len(prices) > 5 else prices

        avg = sum(prices) / len(prices)
        return round5(avg * 0.85), round5(avg * 1.15)

    # LEVEL 3 (median)
    if raw_prices:
        prices = sorted(raw_prices)
        mid = prices[len(prices)//2]

        return round5(mid * 0.9), round5(mid * 1.1)

    return None


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()
    img64 = base64.b64encode(img).decode()

    # priceless mode
    if check_priceless(img64):
        return {
            "description": "wow! priceless..",
            "price_range": "",
            "condition": "middel stand",
            "note": ""
        }

    data = identify(img64)

    name = data.get("name") or ""
    brand = data.get("brand") or ""
    condition = data.get("condition") or ""

    if not name:
        return {
            "description": "Ukendt produkt",
            "price_range": "Ingen pris",
            "condition": "",
            "note": ""
        }

    queries = [
        f"{brand} {name} brugt til salg danmark",
        f"{name} brugt danmark pris",
        f"{name} lignende brugt danmark"
    ]

    all_results = []

    for q in queries:
        res = search(q)
        if res:
            all_results.extend(res)

    filtered = filter_prices(name, all_results)

    result = calculate(filtered, all_results)

    similar_mode = False

    # 🔥 hvis stadig ingen stærk data → brug lignende
    if not result:

        similar_queries = [
            f"{name} lignende brugt danmark",
            f"{name} furniture used price",
            f"{name} similar used price"
        ]

        similar_results = []

        for q in similar_queries:
            res = search(q)
            if res:
                similar_results.extend(res)

        filtered_sim = filter_prices(name, similar_results)

        result = calculate(filtered_sim, similar_results)

        if result:
            similar_mode = True

    if not result:
        return {
            "description": f"{name}\n{brand}",
            "price_range": "Ingen pris fundet",
            "condition": condition,
            "note": ""
        }

    min_p, max_p = result

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{min_p} - {max_p} kr",
        "condition": condition,
        "note": "lignende" if similar_mode else ""
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v10.3-final"}