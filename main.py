from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import google.generativeai as genai

from PIL import Image

from statistics import median

import io
import os
import re
import requests

from bs4 import BeautifulSoup

app = FastAPI()

# ---------------------------------------------------
# CORS
# ---------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# GEMINI 2.5 FLASH
# ---------------------------------------------------

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

# ---------------------------------------------------
# BLACKLIST
# ---------------------------------------------------

BLACKLIST = [

    # farver
    "grøn",
    "grønt",
    "grønne",
    "blå",
    "blåt",
    "rød",
    "rødt",
    "gul",
    "gult",
    "sort",
    "hvid",
    "brun",
    "beige",
    "orange",
    "pink",
    "lilla",
    "sølv",
    "guld",
    "grå",

    # stil/fyld
    "vintage",
    "retro",
    "moderne",
    "klassisk",
    "rustik",
    "minimalistisk",
    "skandinavisk",
    "nordisk",

    # stemning
    "flot",
    "smuk",
    "unik",
    "elegant",
    "sjælden",
    "dekorativ",
    "fantastisk",

    # størrelse/form
    "stor",
    "lille",
    "høj",
    "lav",
    "bred",
    "smal",
    "rund",
    "firkantet",

    # lys/mørk
    "lys",
    "mørk",

    # fyld
    "meget",
    "super",
    "ekstra",

    # støjord
    "voks"
]

# ---------------------------------------------------
# GOOD MATERIALS
# ---------------------------------------------------

GOOD_MATERIALS = [
    "kobber",
    "messing",
    "teak",
    "eg",
    "læder",
    "glas",
    "keramik",
    "marmor",
    "akryl",
    "stål",
    "metal",
    "træ",
    "denim"
]

# ---------------------------------------------------
# GOOD STYLES
# ---------------------------------------------------

GOOD_STYLES = [
    "ribbet",
    "marokkansk",
    "industriel",
    "antik",
    "retro"
]

# ---------------------------------------------------
# CLEAN SEARCH
# ---------------------------------------------------

def clean_search_query(query):

    words = query.split()

    cleaned = []

    for word in words:

        w = word.lower().strip()

        if w not in BLACKLIST:
            cleaned.append(word)

    return " ".join(cleaned)

# ---------------------------------------------------
# DBA SEARCH
# ---------------------------------------------------

def search_dba_prices(query):

    try:

        url = f"https://www.dba.dk/soeg/?soeg={query}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        text = soup.get_text(" ")

        matches = re.findall(
            r'(\d[\d\.]*)\s*kr',
            text
        )

        prices = []

        for m in matches:

            try:

                p = int(
                    m.replace(".", "")
                )

                if 20 <= p <= 200000:
                    prices.append(p)

            except:
                pass

        return prices[:40]

    except Exception as e:

        print("DBA ERROR:", e)

        return []

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok"}

# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(None)):

    print("ANALYZE START")

    if file is None:

        return JSONResponse({
            "success": False,
            "html": """
            <div class='error'>
                Ingen fil modtaget
            </div>
            """
        })

    try:

        image_bytes = await file.read()

        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        # ---------------------------------------------------
        # AI STRUCTURED OUTPUT
        # ---------------------------------------------------

        prompt = """
        Analyser objektet.

        Returner KUN dette format:

        PRODUKT:
        MATERIALE:
        STIL:
        DESIGNER:

        Regler:
        - korte ord
        - ingen sætninger
        - ingen farver
        - ingen vurderinger
        - ingen fyldord
        - ukendt hvis tomt

        Eksempel:

        PRODUKT: lampe
        MATERIALE: akryl
        STIL: ribbet
        DESIGNER: ukendt
        """

        response = model.generate_content([
            prompt,
            image
        ])

        raw = response.text.strip()

        print(raw)

        product = "produkt"
        material = ""
        style = ""
        designer = ""

        for line in raw.splitlines():

            line = line.strip()

            if line.startswith("PRODUKT:"):
                product = line.replace(
                    "PRODUKT:",
                    ""
                ).strip()

            elif line.startswith("MATERIALE:"):
                material = line.replace(
                    "MATERIALE:",
                    ""
                ).strip()

            elif line.startswith("STIL:"):
                style = line.replace(
                    "STIL:",
                    ""
                ).strip()

            elif line.startswith("DESIGNER:"):
                designer = line.replace(
                    "DESIGNER:",
                    ""
                ).strip()

        # ---------------------------------------------------
        # BUILD SEARCH QUERY
        # ---------------------------------------------------

        search_parts = []

        # designer først
        if designer and designer.lower() != "ukendt":
            search_parts.append(designer)

        # godt materiale
        if material and material.lower() in GOOD_MATERIALS:
            search_parts.append(material)

        # stærk stil
        elif style and style.lower() in GOOD_STYLES:
            search_parts.append(style)

        # altid produkt
        search_parts.append(product)

        # max 3 ord
        search_parts = search_parts[:3]

        search_query = " ".join(search_parts)

        search_query = clean_search_query(
            search_query
        )

        print("SEARCH:", search_query)

        # ---------------------------------------------------
        # DBA PRICES
        # ---------------------------------------------------

        prices = search_dba_prices(
            search_query
        )

        print("PRICES:", prices)

        # ---------------------------------------------------
        # SMART PRICE LOGIC
        # ---------------------------------------------------

        if len(prices) > 0:

            prices = sorted(prices)

            trim = int(len(prices) * 0.2)

            if len(prices) > 5:
                prices = prices[trim:-trim]

            realistic_price = int(
                median(prices)
            )

        else:

            # AI fallback
            price_prompt = f"""
            Produkt:
            {search_query}

            Vurder realistisk DBA-brugtpris i Danmark.

            Returner KUN ET TAL.

            Eksempel:
            250
            """

            price_response = model.generate_content(
                price_prompt
            )

            try:

                realistic_price = int(
                    re.findall(
                        r'\d+',
                        price_response.text
                    )[0]
                )

            except:

                realistic_price = 300

        # ---------------------------------------------------
        # DESCRIPTION
        # ---------------------------------------------------

        description_parts = []

        if style and style != "ukendt":
            description_parts.append(style)

        if material and material != "ukendt":
            description_parts.append(material)

        description_parts.append(product)

        description = " ".join(
            description_parts
        ).capitalize()

        # ---------------------------------------------------
        # DBA LINK
        # ---------------------------------------------------

        dba_link = (
            "https://www.dba.dk/soeg/?soeg="
            + search_query
        )

        # ---------------------------------------------------
        # HTML
        # ---------------------------------------------------

        html = f"""
        <div class="result-box">

            <div class="result-title">
                {description}
            </div>

            <div class="result-price">
                Pris: {realistic_price} kr
            </div>

        </div>
        """

        return JSONResponse({
            "success": True,
            "html": html,
            "search_query": search_query,
            "dba_link": dba_link
        })

    except Exception as e:

        print("SERVER ERROR:", str(e))

        return JSONResponse({
            "success": False,
            "html": f"""
            <div class='error'>
                Fejl: {str(e)}
            </div>
            """
        })