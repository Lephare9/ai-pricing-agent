print("🔥 OPENAI VERSION ACTIVE 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import re
import json
import base64

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- AI ----------
def analyze_image_with_ai(image_bytes):
    print("🔥 FUNCTION STARTED")

    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Returnér KUN JSON: {\"name\":\"kort navn\",\"price\":123}"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=200,
        )

        text = response.choices[0].message.content
        print("🔥 AI RAW:", text)

        return text if text else '{"name":"ukendt","price":0}'

    except Exception as e:
        print("🔥 AI FEJL:", str(e))
        return '{"name":"ukendt","price":0}'


# ---------- JSON ----------
def extract_json(text):
    try:
        print("🔥 PARSER INPUT:", text)

        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())

            if isinstance(data.get("price"), str):
                data["price"] = int(re.sub(r"\D", "", data["price"]) or 0)

            return data

    except Exception as e:
        print("🔥 JSON FEJL:", str(e))

    return {"name": "ukendt", "price": 0}


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("🔥 ENDPOINT HIT")

    image_bytes = await file.read()

    ai_response = analyze_image_with_ai(image_bytes)
    data = extract_json(ai_response)

    return {
        "description": data.get("name", "ukendt"),
        "price": data.get("price", 0)
    }


@app.get("/")
def root():
    return {"status": "ok"}