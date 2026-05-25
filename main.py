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
import re

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

        async with httpx.AsyncClient(timeout=20) as client:

            response = await client.get(
                url,
                headers=headers,
                follow_redirects=True
            )

        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text(" ", strip=True)

        matches = re.findall(
            r'(\d{2,6})\s?kr',
            text,
            re.IGNORECASE
        )

        prices = []

        for m in matches:

            try:

                price = int(m)

                if 50 <= price <= 100000:
                    prices.append(price)

            except:
                pass

        prices = list(set(prices))

        prices.sort()

        return prices[:50], url

    except Exception as e:

        print("DBA ERROR:", e)

        return [], url


# ---------------------------------------------------
# PRICE ESTIMATION
# ---------------------------------------------------

def estimate_price(prices, description):

    if not prices:
        return "Ukendt"

    median = statistics.median(prices)

    low = int(median * 0.85)
    high = int(median * 1.15)

    text = description.lower()

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

    is_design = any(
        word in text
        for word in design_words
    )

    # Only upscale real design items
    if is_design and median < 1500:

        low = int(median * 1.8)
        high = int(median * 2.8)

    return f"{low}-{high} kr"


# ---------------------------------------------------
# FRONTEND
# ---------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():

    with open(
        "index.html",
        encoding="utf-8"
    ) as f:

        return f.read()


# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(
    image: UploadFile = File(...)
):

    temp_path = None
    jpeg_path = None

    try:

        print("ANALYZE START")

        suffix = os.path.splitext(
            image.filename
        )[1]

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        ) as tmp:

            content = await image.read()

            tmp.write(content)

            temp_path = tmp.name

        # ---------------------------------------------------
        # FORCE CONVERT EVERYTHING TO REAL JPEG
        # Fixes iPhone HEIC / MPO / Safari uploads
        # ---------------------------------------------------

        img = Image.open(temp_path)

        if img.mode != "RGB":
            img = img.convert("RGB")

        jpeg_path = temp_path + ".jpg"

        img.save(
            jpeg_path,
            "JPEG",
            quality=90
        )

        img = Image.open(jpeg_path)

        # ---------------------------------------------------
        # AI ANALYSIS
        # ---------------------------------------------------

        prompt = """
Beskriv varen meget kort og præcist.

Regler:
- max 5 ord
- kun produkttype + materiale/stil
- ingen lange sætninger
- ingen fyldord

Eksempler:
Traditionel marokkansk læderpuf
PH bordlampe
Vintage teak kommode
Design væglampe i metal
"""

        response = model.generate_content(
            [prompt, img]
        )

        description = response.text.strip()

        print("DESCRIPTION:", description)

        # ---------------------------------------------------
        # SEARCH DBA
        # ---------------------------------------------------

        prices, dba_url = await search_dba(
            description
        )

        print("DBA PRICES:", prices[:10])

        estimated = estimate_price(
            prices,
            description
        )

        # ---------------------------------------------------
        # RESULT HTML
        # ---------------------------------------------------

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

        # ---------------------------------------------------
        # CLEANUP
        # ---------------------------------------------------

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        if jpeg_path and os.path.exists(jpeg_path):
            os.remove(jpeg_path)

        return {
            "result": result
        }

    except Exception as e:

        print("SERVER ERROR:", str(e))

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        if jpeg_path and os.path.exists(jpeg_path):
            os.remove(jpeg_path)

        return {
            "result": f"Fejl: {str(e)}"
        }