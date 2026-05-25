from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import google.generativeai as genai
from PIL import Image
import tempfile
import os
import urllib.parse
import httpx
from bs4 import BeautifulSoup
import statistics

app = FastAPI()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel("gemini-2.5-flash")

# ---------------------------------------------------
# DBA SEARCH
# ---------------------------------------------------

async def search_dba(query):

    encoded = urllib.parse.quote(query)

    url = f"https://www.dba.dk/soeg/?soeg={encoded}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:

            response = await client.get(
                url,
                headers=headers,
                follow_redirects=True
            )

        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        prices = []

        text = soup.get_text(" ", strip=True)

        import re

        matches = re.findall(r'(\d{2,6})\s?kr', text)

        for m in matches:

            try:
                price = int(m)

                if 50 <= price <= 100000:
                    prices.append(price)

            except:
                pass

        prices = list(set(prices))

        prices.sort()

        return prices[:40], url

    except Exception as e:
        print("DBA ERROR:", e)
        return [], url


# ---------------------------------------------------
# PRICE ESTIMATION
# ---------------------------------------------------

def estimate_price(prices, ai_text):

    if not prices:
        return "Ukendt"

    median = statistics.median(prices)

    low = int(median * 0.85)
    high = int(median * 1.15)

    text = ai_text.lower()

    design_words = [
        "designer",
        "design",
        "ikonisk",
        "ph",
        "louis poulsen",
        "verner panton",
        "kartell",
        "flos"
    ]

    is_design = any(word in text for word in design_words)

    if is_design and median < 1200:
        low = int(median * 1.8)
        high = int(median * 2.8)

    return f"{low}-{high} kr"


# ---------------------------------------------------
# FRONTEND
# ---------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():

    with open("index.html", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(
    image: UploadFile = File(...)
):

    try:

        suffix = os.path.splitext(image.filename)[1]

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:

            content = await image.read()

            tmp.write(content)

            temp_path = tmp.name

        img = Image.open(temp_path)

        prompt = """
Beskriv varen kort og præcist.

Regler:
- max 5 ord
- meget konkret
- ingen lange beskrivelser
- kun type + materiale/stil hvis relevant

Eksempler:
Traditionel marokkansk læderpuf
Design væglampe i metal
PH bordlampe
Vintage teak kommode
"""

        response = model.generate_content([prompt, img])

        description = response.text.strip()

        prices, dba_url = await search_dba(description)

        estimated = estimate_price(prices, description)

        result = f"""
<div class="result-card">

<div class="result-text">
{description}<br><br>
Pris: {estimated}
</div>

<a
href="{dba_url}"
target="_blank"
class="link-btn"
>
Se lignende
</a>

</div>
"""

        os.remove(temp_path)

        return {
            "result": result
        }

    except Exception as e:

        print("SERVER ERROR:", str(e))

        return {
            "result": f"Fejl: {str(e)}"
        }