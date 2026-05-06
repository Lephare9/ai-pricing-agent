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
        contents = await file.read()
        image_base64 = base64.b64encode(contents).decode()

        # ------------------------
        # 1. GEMINI (object + text)
        # ------------------------
        try:
            model = genai.GenerativeModel("gemini-1.5-flash-latest")

            response = model.generate_content([
                {"mime_type": "image/jpeg", "data": contents},
                """Hvad er objektet? (kort svar)
                Er der tekst på objektet? skriv den også.
                Format:
                OBJECT: ...
                TEXT: ...
                """
            ])

            result = response.text.lower()

            object_desc = "ukendt objekt"
            text_found = ""

            if "object:" in result:
                object_desc = result.split("object:")[1].split("\n")[0].strip()

            if "text:" in result:
                text_found = result.split("text:")[1].strip()

        except Exception as e:
            print("Gemini fejl:", e)
            object_desc = "ukendt objekt"
            text_found = ""

        print("OBJECT:", object_desc)
        print("TEXT:", text_found)

        # ------------------------
        # 2. SEARCH (DBA / SALG)
        # ------------------------
        queries = [
            f"{object_desc} dba",
            f"{object_desc} til salg",
            f"{object_desc} marketplace",
            f"{object_desc} vintage"
        ]

        if text_found:
            queries.insert(0, f"{text_found} dba")

        prices = []

        for query in queries:
            try:
                print("Searching:", query)

                params = {
                    "engine": "google",
                    "q": query,
                    "api_key": SERP_API_KEY
                }

                r = requests.get("https://serpapi.com/search", params=params)

                try:
                    data = r.json()
                except:
                    print("Ikke JSON:", r.text)
                    continue

                for res in data.get("organic_results", [])[:5]:
                    snippet = res.get("snippet", "").lower()

                    # skip nypris
                    if "ny" in snippet:
                        continue

                    digits = ''.join(c for c in snippet if c.isdigit())

                    if digits:
                        price = int(digits)

                        # filter støj
                        if 20 < price < 5000:
                            prices.append(price)

            except Exception:
                print("Query fejlede:", query)

        # ------------------------
        # 3. FALLBACK: LENS
        # ------------------------
        if not prices:
            try:
                print("Fallback: Google Lens")

                params = {
                    "engine": "google_lens",
                    "api_key": SERP_API_KEY,
                    "image_base64": image_base64
                }

                r = requests.get("https://serpapi.com/search", params=params)
                data = r.json()

                for item in data.get("visual_matches", [])[:5]:
                    price_str = item.get("price", "")
                    digits = ''.join(c for c in price_str if c.isdigit())

                    if digits:
                        price = int(digits)
                        if 20 < price < 5000:
                            prices.append(price)

            except:
                print("Lens fejlede")

        # ------------------------
        # 4. FINAL PRICE (median)
        # ------------------------
        if prices:
            prices = sorted(prices)
            mid = len(prices) // 2
            final_price = prices[mid]
        else:
            # sidste fallback
            if "kasse" in object_desc:
                final_price = 80
            elif "stol" in object_desc:
                final_price = 250
            else:
                final_price = 100

        return {
            "description": object_desc,
            "price": f"{final_price} kr"
        }

    except Exception:
        print("TOTAL CRASH:")
        print(traceback.format_exc())
        return {"description": "Systemfejl", "price": "0 kr"}