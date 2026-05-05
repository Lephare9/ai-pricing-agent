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
        text = text.replace("```json", "").replace("```", "")
        return json.loads(text[text.find("{"):text.rfind("}")+1])
    except:
        return {}


# ---------- IDENTIFY ----------
def identify(image):

    prompt = """
Identificér produkt præcist.

Returnér JSON:
{
 "name": "",
 "brand": "",
 "condition": ""
}
"""

    raw = call_gemini(prompt, image)
    return extract_json(raw) if raw else {}


# ---------- DBA SCRAPER ----------
def search_dba(query):

    url = f"https://www.dba.dk/soeg/?soeg={query.replace(' ', '+')}"

    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        prices = []

        for p in soup.find_all(text=re.compile("kr")):
            text = str(p)

            match = re.search(r"(\d{2,5})\s*kr", text.lower())
            if match:
                val = int(match.group(1))

                if 20 < val < 50000:
                    prices.append(val)

        print("DBA:", prices[:10])

        return prices[:15]

    except Exception as e:
        print("DBA ERROR:", e)
        return []


# ---------- GULOGGRATIS ----------
def search_guloggratis(query):

    url = f"https://www.guloggratis.dk/s/q-{query.replace(' ', '%20')}"

    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        prices = []

        for p in soup.find_all(text=re.compile("kr")):
            text = str(p)

            match = re.search(r"(\d{2,5})\s*kr", text.lower())
            if match:
                val = int(match.group(1))

                if 20 < val < 50000:
                    prices.append(val)

        print("GULOG:", prices[:10])

        return prices[:10]

    except:
        return []


# ---------- CALC ----------
def round5(x):
    return int(round(x / 5) * 5)


def calculate(prices):

    if not prices:
        return None

    prices = sorted(prices)

    if len(prices) > 5:
        cut = max(1, int(len(prices) * 0.2))
        prices = prices[cut:-cut]

    avg = sum(prices) / len(prices)

    return round5(avg * 0.9), round5(avg * 1.1)


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    img = await file.read()
    img64 = base64.b64encode(img).decode()

    data = identify(img64)

    name = data.get("name") or ""
    brand = data.get("brand") or ""
    condition = data.get("condition") or ""

    print("IDENT:", name, brand)

    if not name:
        return {
            "description": "Ukendt produkt",
            "price_range": "Ingen pris",
            "condition": "",
            "note": ""
        }

    query = f"{brand} {name}".strip()

    # 🔥 DBA først
    prices = search_dba(query)

    note = ""

    # 🔁 fallback
    if len(prices) < 3:
        print("FALLBACK GULOGGRATIS")
        more = search_guloggratis(query)
        prices.extend(more)

        if more:
            note = "lignende"

    result = calculate(prices)

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
        "note": note
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v11-real-data"}