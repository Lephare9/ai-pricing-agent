from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai

from PIL import Image
import io
import os
import re
import urllib.parse

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GEMINI KEY
genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

# MODEL
model = genai.GenerativeModel("gemini-2.5-flash")

PROMPT = """
Du er en dansk prisagent.

Analyser billedet og vurder hvad varen er.

Svar KUN i dette format:

Produktbeskrivelse

Pris: xxx-xxx kr

Regler:
- Kort præcis beskrivelse
- Ingen "Navn:"
- Ingen ekstra tekst
- Smalt realistisk prisinterval
- Typisk cirka 15%
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/analyze")
async def analyze(
    image1: UploadFile = File(...),
    image2: UploadFile = File(None)
):

    try:

        images = []

        for file in [image1, image2]:

            if not file:
                continue

            contents = await file.read()

            # ÅBN BILLEDE
            img = Image.open(io.BytesIO(contents))

            # FIX MPO / HEIC / RGBA
            if img.mode != "RGB":
                img = img.convert("RGB")

            # SKALER NED
            img.thumbnail((1600, 1600))

            # GEM SOM JPEG
            temp_buffer = io.BytesIO()

            img.save(
                temp_buffer,
                format="JPEG",
                quality=85
            )

            jpeg_bytes = temp_buffer.getvalue()

            images.append({
                "mime_type": "image/jpeg",
                "data": jpeg_bytes
            })

        # GEMINI REQUEST
        response = model.generate_content(
            [PROMPT] + images
        )

        result_text = response.text.strip()

        # DBA LINK
        first_line = result_text.split("\n")[0]
        search_query = urllib.parse.quote(first_line)

        dba_link = f"https://www.dba.dk/soeg/?soeg={search_query}"

        return JSONResponse({
            "result": result_text,
            "dba_link": dba_link
        })

    except Exception as e:

        print("ERROR:", str(e))

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )