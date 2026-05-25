from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import google.generativeai as genai

from PIL import Image

import io
import os

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# GEMINI
# -----------------------------

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel("gemini-2.5-flash")

# -----------------------------
# ROOT
# -----------------------------

@app.get("/")
async def root():
    return {"status": "ok"}

# -----------------------------
# ANALYZE
# -----------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(None)):

    print("ANALYZE START")

    # undgå 422
    if file is None:

        print("NO FILE")

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

        # pil image
        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGB")

        # ai analyse
        response = model.generate_content([
            """
            Beskriv produktet meget kort på dansk.

            Regler:
            - kun produkttype
            - maks 4 ord
            - ingen lange beskrivelser
            - ingen sætninger

            Eksempler:
            Marokkansk læderpuf
            Ribbet akryl pendel
            Designer glaslampe
            """,
            image
        ])

        description = response.text.strip()

        print("DESCRIPTION:", description)

        desc = description.lower()

        # -----------------------------
        # PRISLOGIK
        # -----------------------------

        low_price = 300
        high_price = 900

        # puf
        if "puf" in desc:

            low_price = 300
            high_price = 600

        # lampe design
        elif (
            "lampe" in desc
            or "pendel" in desc
            or "akryl" in desc
            or "ribbet" in desc
            or "designer" in desc
        ):

            low_price = 1500
            high_price = 4500

        # -----------------------------
        # HTML
        # -----------------------------

        html = f"""
        <div class="result-box">

            <div class="result-title">
                {description}
            </div>

            <div class="result-price">
                Pris: {low_price}-{high_price} kr
            </div>

        </div>
        """

        print("SUCCESS")

        return JSONResponse({
            "success": True,
            "html": html
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