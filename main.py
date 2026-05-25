from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse

import google.generativeai as genai

from PIL import Image

import tempfile
import shutil
import urllib.parse
import os

app = FastAPI()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

PROMPT = """
Du vurderer brugtpriser i Danmark.

Beskriv varen kort på én linje.

Skriv derefter:
Pris: xxx kr

Pris skal være realistisk og relativt smalt interval.
Brug cirka ±15%.

Undgå brede intervaller.

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
        print("========================")
        print("ANALYZE CALLED")
        print("========================")

        images = []

        for file in [image1, image2]:

            if not file:
                continue

            print("")
            print("========================")
            print("PROCESSING IMAGE")
            print("========================")

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".jpg"
            )

            with open(
                temp_file.name,
                "wb"
            ) as buffer:

                shutil.copyfileobj(
                    file.file,
                    buffer
                )

            image = Image.open(
                temp_file.name
            )

            print("ORIGINAL SIZE:", image.size)

            image.thumbnail((1200,1200))

            print("THUMBNAIL SIZE:", image.size)

            clean_path = (
                temp_file.name + "_clean.jpg"
            )

            image.convert("RGB").save(
                clean_path,
                "JPEG",
                quality=85
            )

            final_image = Image.open(
                clean_path
            )

            images.append(final_image)

        print("")
        print("========================")
        print("TOTAL IMAGES:", len(images))
        print("========================")

        print("")
        print("========================")
        print("CALLING GEMINI")
        print("========================")

        response = model.generate_content(
            [PROMPT] + images
        )

        text = response.text.strip()

        text = text.replace("Navn:", "")
        text = text.replace("navn:", "")

        text = text.strip()

        print("")
        print("========================")
        print("GEMINI RESPONSE")
        print("========================")
        print(text)

        first_line = (
            text.split("\n")[0]
        )

        search_query = urllib.parse.quote(
            first_line
        )

        dba_link = (
            f"https://www.dba.dk/soeg/?soeg={search_query}"
        )

        return {
            "result": text,
            "dba_link": dba_link
        }

    except Exception as e:

        print("")
        print("========================")
        print("ERROR")
        print("========================")
        print(str(e))
        print("")

        return {
            "error": str(e)
        }