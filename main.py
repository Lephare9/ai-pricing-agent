from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai

from PIL import Image
import tempfile
import shutil
import os
import urllib.parse

app = FastAPI()

# CORS FIX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GEMINI API KEY FRA RAILWAY VARIABLES
genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT = """
Du vurderer brugtpriser i Danmark.

Analyser billederne og vurder hvad produktet er.

Svar KUN i dette format:

Beskrivelse: xxx

Pris: xxx-xxx kr

Kort og præcist.

Undgå brede prisintervaller.
Brug realistisk dansk brugtpris.

Hvis muligt:
- nævn materiale
- stil/design
- type møbel/objekt

Returner kun svaret.
"""

@app.get("/", response_class=HTMLResponse)
async def root():

    with open(
        "index.html",
        encoding="utf-8"
    ) as f:

        return f.read()


@app.post("/analyze")
async def analyze(
    image1: UploadFile = File(...),
    image2: UploadFile = File(None)
):

    try:

        print("")
        print("================================")
        print("ANALYZE CALLED")
        print("================================")

        images = []

        for file in [image1, image2]:

            if not file:
                continue

            print(f"Processing: {file.filename}")

            with tempfile.NamedTemporaryFile(delete=False) as temp_file:

                shutil.copyfileobj(
                    file.file,
                    temp_file
                )

                image_path = temp_file.name

            image = Image.open(image_path)

            # KONVERTER TIL RGB
            if image.mode != "RGB":
                image = image.convert("RGB")

            # SKALERING
            max_size = 1200

            image.thumbnail((max_size, max_size))

            images.append(image)

            print(f"Image resized: {image.size}")

        print("Sending to Gemini...")

        response = model.generate_content(
            [PROMPT] + images
        )

        result = response.text.strip()

        print("Gemini response received")
        print(result)

        # DBA LINK
        first_line = result.split("\n")[0]

        search_text = (
            first_line
            .replace("Beskrivelse:", "")
            .strip()
        )

        encoded_search = urllib.parse.quote(search_text)

        dba_link = (
            f"https://www.dba.dk/soeg/?soeg={encoded_search}"
        )

        return {
            "result": result,
            "dba_link": dba_link
        }

    except Exception as e:

        print("")
        print("================================")
        print("SERVER ERROR")
        print("================================")
        print(str(e))

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )