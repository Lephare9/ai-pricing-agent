from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import base64
import os

app = FastAPI()

# CORS (MEGET vigtig for Netlify → Railway)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERP_API_KEY = os.getenv("SERP_API_KEY")


@app.get("/")
def root():
    return {"status": "ok - v17.2 debug"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        print("=== HIT ANALYZE ===")

        image_bytes = await file.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # ---------------- GEMINI ----------------
        prompt = """
Beskriv objektet meget præcist på dansk:
materiale, farve, type, stand.

Svar KUN:
kort præcis beskrivelse uden ekstra tekst
"""

        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

        gemini_payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
                ]
            }]
        }

        gemini_res = requests.post(gemini_url, json=gemini_payload)
        print("Gemini status:", gemini_res.status_code)

        gemini_json = gemini_res.json()
        print("Gemini response:", gemini_json)

        description = gemini_json["candidates"][0]["content"]["parts"][0]["text"]
        description = description.strip().capitalize()

        print("Description:", description)

        # ---------------- SERP ----------------
        search_query = description

        serp_url = "https://serpapi.com/search.json"
        serp_params = {
            "q": search_query,
            "api_key": SERP_API_KEY,
            "engine": "google",
            "hl": "da",
            "gl": "dk"
        }

        serp_res = requests.get(serp_url, params=serp_params)
        print("SERP status:", serp_res.status_code)

        serp_json = serp_res.json()
        print("SERP response:", serp_json)

        prices = []

        # Extract priser fra snippets
        if "organic_results" in serp_json:
            for r in serp_json["organic_results"]:
                snippet = r.get("snippet", "")
                words = snippet.split()
                for w in words:
                    if "kr" in w.lower():
                        try:
                            num = int("".join(filter(str.isdigit, w)))
                            if 10 < num < 50000:
                                prices.append(num)
                        except:
                            pass

        print("Prices found:", prices)

        if prices:
            avg_price = int(sum(prices) / len(prices))
            price = f"{avg_price} kr"
        else:
            price = "Ingen pris fundet"

        return {
            "description": description,
            "price": price
        }

    except Exception as e:
        print("🔥 ERROR:", str(e))
        return {
            "description": "Systemfejl",
            "price": "0 kr"
        }