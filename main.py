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

    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=15)
            data = r.json()

            if "candidates" not in data:
                print("GEMINI ERROR:", data)
                time.sleep(1)
                continue

            return data["candidates"][0]["content"]["parts"][0]["text"]

        except Exception as e:
            print("ERROR:", e)
            time.sleep(1)

    return None


# ---------- IDENTIFY (FIXED) ----------
def identify(image):

    prompt = """
Identificér produkt fra billede.

KRAV:
- svar KUN i JSON
- ingen ekstra tekst

Format:
{
 "name": "",
 "brand": "",
 "condition": ""
}
"""

    raw = call_gemini(prompt, image)
    print("RAW GEMINI:", raw)

    if not raw:
        return {}

    try:
        return json.loads(raw)
    except:
        try:
            cleaned = raw[raw.find("{"):raw.rfind("}")+1]
            return json.loads(cleaned)
        except:
            return {}


# ---------- DBA SCRAPER (FIXED) ----------
def search_dba(query):

    url = f"https://www.dba.dk/soeg/?soeg={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        text = soup.get_text(" ")

        matches = re.findall(r"(\d{2,5})[\s.,-]*kr", text.lower())

        prices = [int(m) for m in matches if 20 < int(m) < 50000]

        print("DBA PRICES:", prices[:10])

        return prices[:15]

    except Exception as e:
        print("DBA ERROR:", e)
        return []


# ---------- FALLBACK SEARCH ----------
def search_fallback(query):

    # simpel fallback (bredere)
    return search_dba(query + " brugt")


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

    print("IDENT DATA:", data)

    name = data.get("name") or ""
    brand = data.get("brand") or ""
    condition = data.get("condition") or ""

    # 🔴 fallback hvis identify fejler
    if not name:
        print("IDENT FAILED → fallback name")
        name = "brugt produkt"

    query = f"{brand} {name}".strip()

    # 🔍 PRIMARY (DBA)
    prices = search_dba(query)

    similar_mode = False

    # 🔁 fallback hvis få priser
    if len(prices) < 3:
        print("TRY FALLBACK SEARCH")
        more = search_fallback(name)

        if more:
            prices.extend(more)
            similar_mode = True

    result = calculate(prices)

    # 🔴 sidste fallback → median hvis noget findes
    if not result and prices:
        prices = sorted(prices)
        mid = prices[len(prices)//2]
        result = (round5(mid * 0.9), round5(mid * 1.1))
        similar_mode = True

    # 🔴 absolut fallback (alt fejler)
    if not result:
        result = (100, 300)
        similar_mode = True

    min_p, max_p = result

    return {
        "description": f"{name}\n{brand}",
        "price_range": f"{min_p} - {max_p} kr",
        "condition": condition,
        "note": "lignende" if similar_mode else ""
    }


@app.get("/")
def root():
    return {"status": "ok", "mode": "v11.1-stable"}