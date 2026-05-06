import os
import base64
import requests
import statistics
import re
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai

app = FastAPI()

# CORS (vigtigt)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keys
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

model = genai.GenerativeModel("gemini-1.5-flash")


# ------------------------
# HELPERS
# ------------------------

def extract_prices(text):
    prices = re.findall(r"\d{2,6}", text)
    cleaned = [int(p) for p in prices if 10 < int(p) < 50000]
    return cleaned


def serpapi_google_lens(image_base64):
    url = "https://serpapi.com/search"

    params = {
        "engine": "google_lens",
        "api_key": SERPAPI_KEY,
        "image_content": image_base64
    }

    response = requests.get(url, params=params)
    data = response.json()

    prices = []

    # visuelle matches
    for item in data.get("visual_matches", []):
        if "price" in item:
            prices += extract_prices(item["price"])

    return prices


def serpapi_text_search(query):
    url = "https://serpapi.com/search"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    prices = []

    for result in data.get("organic_results", []):
        text = result.get("title", "") + " " + result.get("snippet", "")
        prices += extract_prices(text)

    return prices


# ------------------------
# MAIN ENDPOINT
# ------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze called ===")

    image_bytes = await file.read()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    # ------------------------
    # 1. GEMINI ANALYSE
    # ------------------------

    try:
        response = model.generate_content([
            {
                "mime_type": "image/jpeg",
                "data": image_base64
            },
            """
            Hvad er dette objekt?
            Er der tekst på objektet?
            Returnér:
            - kort navn
            - tekst hvis nogen
            """
        ])

        gemini_text = response.text.lower()
        print("Gemini:", gemini_text)

    except Exception as e:
        print("Gemini fejl:", e)
        gemini_text = ""

    # ------------------------
    # 2. GOOGLE LENS (IMAGE SEARCH)
    # ------------------------

    print("🔎 Google Lens search...")
    prices = serpapi_google_lens(image_base64)
    print("Lens prices:", prices)

    # ------------------------
    # 3. FALLBACK: tekst søgning
    # ------------------------

    if len(prices) < 3:
        print("🔎 Text fallback...")

        query = gemini_text.strip()

        if len(query) < 5:
            query = "brugt møbel"

        more_prices = serpapi_text_search(query)
        print("Text prices:", more_prices)

        prices += more_prices

    # ------------------------
    # 4. FALLBACK: generisk kategori
    # ------------------------

    if len(prices) < 3:
        print("🔎 Generic fallback...")

        generic_prices = serpapi_text_search("trækasse brugt")
        prices += generic_prices

    # ------------------------
    # 5. PRIS BEREGNING
    # ------------------------

    if prices:
        price = int(statistics.median(prices))
    else:
        price = 75  # fallback baseline

    # ------------------------
    # 6. BESKRIVELSE
    # ------------------------

    description = gemini_text.split("\n")[0][:50]

    if not description:
        description = "genstand"

    print("FINAL:", description, price)

    return {
        "description": description,
        "price": f"{price} kr"
    }