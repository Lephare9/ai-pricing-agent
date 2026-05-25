from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import google.generativeai as genai

from PIL import Image

import io
import os
import re

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
# GEMINI
# ---------------------------------------------------

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel("gemini-2.5-flash")

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
            <div class="error">
                Ingen fil modtaget
            </div>
            """
        })

    try:

        print("FILENAME:", file.filename)
        print("CONTENT TYPE:", file.content_type)

        image_bytes = await file.read()

        print("BYTES:", len(image_bytes))

        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        # ---------------------------------------------------
        # AI ANALYSE
        # ---------------------------------------------------

        prompt = """
        Analyser produktet på billedet.

        Returner KUN dette format:

        BESKRIVELSE: kort naturlig beskrivelse
        SØGNING: korte DBA-søgeord uden farver
        PRIS: realistisk brugtpris i Danmark

        Regler:
        - fjern farver i søgestreng
        - maks 3-4 søgeord
        - fokus på produkttype
        - vurder realistisk DBA/brugtpris
        - almindelige massevarer skal være billige
        - designobjekter må være dyrere
        - undgå vilde overdrivelser

        Eksempel:

        BESKRIVELSE: Grøn udskåret trææske
        SØGNING: trææske udskåret
        PRIS: 75-200 kr

        BESKRIVELSE: Fujitsu computermus
        SØGNING: computermus Fujitsu
        PRIS: 50-100 kr

        BESKRIVELSE: Ribbet designerlampe
        SØGNING: ribbet lampe
        PRIS: 1800-3500 kr
        """

        response = model.generate_content([
            prompt,
            image
        ])

        text = response.text.strip()

        print("RAW AI:")
        print(text)

        description = ""
        search_query = ""
        price = ""

        for line in text.splitlines():

            line = line.strip()

            if line.startswith("BESKRIVELSE:"):
                description = line.replace(
                    "BESKRIVELSE:",
                    ""
                ).strip()

            elif line.startswith("SØGNING:"):
                search_query = line.replace(
                    "SØGNING:",
                    ""
                ).strip()

            elif line.startswith("PRIS:"):
                price = line.replace(
                    "PRIS:",
                    ""
                ).strip()

        # ---------------------------------------------------
        # FALLBACKS
        # ---------------------------------------------------

        if not description:
            description = "Ukendt produkt"

        if not search_query:
            search_query = description

        if not price:
            price = "100-500 kr"

        print("DESCRIPTION:", description)
        print("SEARCH:", search_query)
        print("PRICE:", price)

        # ---------------------------------------------------
        # HTML
        # ---------------------------------------------------

        html = f"""
        <div class="result-box">

            <div class="result-title">
                {description}
            </div>

            <div class="result-price">
                Pris: {price}
            </div>

        </div>
        """

        return JSONResponse({
            "success": True,
            "html": html,
            "search_query": search_query
        })

    except Exception as e:

        print("SERVER ERROR:", str(e))

        return JSONResponse({
            "success": False,
            "html": f'''
            <div class="error">
                Fejl: {str(e)}
            </div>
            '''
        })