from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64
import google.generativeai as genai
import traceback

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
SERP_API_KEY = os.getenv("SERP_API_KEY")


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        print("=== /analyze called ===")

        contents = await file.read()
        image_base64 = base64.b64encode(contents).decode()

        # ------------------------
        # 1. GEMINI ANALYSE
        # ------------------------
        try:
            model = genai.GenerativeModel("gemini-1.5-flash-latest")

            response = model.generate_content([
                {"mime_type": "image/jpeg", "data": contents},
                "Hvad er dette objekt? Beskriv kort og nævn tekst på objektet hvis muligt."
            ])

            description = response.text.lower()
            print("Gemini:", description)

        except Exception as e:
            print("Gemini fejl:", e)
            description = "ukendt objekt"

        # ------------------------
        # 2. GOOGLE LENS (SerpAPI)
        # ------------------------
        prices = []

        try:
            params = {
                "engine": "google_lens",
                "api_key": SERP_API_KEY,
                "image_base64": image_base64
            }

            r = requests.get("https://serpapi.com/search", params=params)

            try:
                data = r.json()
            except Exception:
                print("SerpAPI ikke JSON:", r.text)
                data = {}

            visual_matches = data.get("visual_matches", [])

            for item in visual_matches[:5]:
                title = item.get("title", "")
                price_str = item.get("price", "")

                if price_str:
                    price_num = ''.join(c for c in price_str if c.isdigit())
                    if price_num:
                        prices.append(int(price_num))

        except Exception:
            print("SerpAPI crash:")
            print(traceback.format_exc())

        # ------------------------
        # 3. FALLBACK LOGIK
        # ------------------------
        if prices:
            avg_price = int(sum(prices) / len(prices))
        else:
            print("Ingen priser → fallback")

            if "kasse" in description or "crate" in description:
                avg_price = 80
            elif "stol" in description:
                avg_price = 250
            else:
                avg_price = 100

        return {
            "description": description,
            "price": f"{avg_price} kr"
        }

    except Exception:
        print("TOTAL CRASH:")
        print(traceback.format_exc())
        return {"description": "Systemfejl", "price": "0 kr"}