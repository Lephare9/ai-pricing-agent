from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from statistics import median
from PIL import Image
import io
import re
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-1.5-flash")


# FJERN FARVER FRA SØGNING
BLACKLIST_WORDS = [
    "grøn",
    "grønt",
    "blå",
    "blåt",
    "rød",
    "rødt",
    "gul",
    "gult",
    "sort",
    "hvid",
    "brun",
    "sølv",
    "sølvfarvet",
    "gammel",
    "vintage",
    "retro"
]


def clean_search_query(text):
    words = text.lower().split()

    filtered = []

    for w in words:
        if w not in BLACKLIST_WORDS:
            filtered.append(w)

    return " ".join(filtered)


def search_dba_prices(search_query):

    url = f"https://www.dba.dk/soeg/?soeg={search_query}"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers, timeout=15)

    soup = BeautifulSoup(response.text, "html.parser")

    text = soup.get_text(" ")

    matches = re.findall(r'(\d[\d\.]*)\s*kr', text)

    prices = []

    for m in matches:

        try:

            p = int(m.replace(".", ""))

            if 20 <= p <= 200000:
                prices.append(p)

        except:
            pass

    return prices[:40]


@app.get("/")
async def root():

    return {"status": "running"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        contents = await file.read()

        image = Image.open(io.BytesIO(contents))

        prompt = """
        Beskriv varen meget kort til DBA-søgning.

        Regler:
        - maks 4 ord
        - ingen farver
        - ingen vurdering
        - ingen størrelse
        - kun produkttype

        Eksempler:
        "marokkansk læderpuf"
        "kablet computermus"
        "design væglampe"
        "udskåret trææske"
        """

        response = model.generate_content([prompt, image])

        description = response.text.strip()

        description = clean_search_query(description)

        print("DESCRIPTION:", description)

        prices = search_dba_prices(description)

        print("DBA PRICES:", prices)

        if len(prices) >= 3:

            realistic_price = int(min(prices))

        elif len(prices) > 0:

            realistic_price = int(min(prices))

        else:

            realistic_price = 300

        dba_link = f"https://www.dba.dk/soeg/?soeg={description}"

        html = f"""
        <div class="result-box">

            <div class="result-title">
                {description.capitalize()}
            </div>

            <div class="result-price">
                Pris: {realistic_price} kr
            </div>

        </div>

        <div style="text-align:center;margin-top:30px;">

            <a href="{dba_link}"
               target="_blank"
               style="
                    display:inline-block;
                    background:#5b8cff;
                    color:white;
                    text-decoration:none;
                    padding:22px 46px;
                    border-radius:24px;
                    font-size:34px;
                    font-weight:bold;
               ">
               Se lignende
            </a>

        </div>
        """

        return {"html": html}

    except Exception as e:

        print("SERVER ERROR:", str(e))

        return {
            "html": """
            <div class='error'>
                Serverfejl
            </div>
            """
        }