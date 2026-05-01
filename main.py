print("🔥 OPENAI VERSION ACTIVE 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import re
import json
import base64

# 🔑 OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# 🌐 CORS
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
                        {
                            "type": "text",
                            "text": (
                                "Estimate realistic resale price in DKK.\n"
                                "Return ONLY valid JSON. No markdown.\n"
                                "{\"name\":\"short product name\",\"price\":123,\"reason\":\"short explanation\"}"
                            ),
                        },
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

        return text if text else '{"name":"unknown","price":0,"reason":""}'

    except Exception as e:
        print("🔥 AI FEJL:", str(e))
        return '{"name":"unknown","price":0,"reason":""}'


# ---------- JSON ----------
def extract_json(text):
    try:
        print("🔥 PARSER INPUT:", text)

        # fjern markdown hvis AI alligevel sender det
        text = text.replace("```json", "").replace("```", "").strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())

            # fix hvis price er string
            if isinstance(data.get("price"), str):
                data["price"] = int(re.sub(r"\D", "", data["price"]) or 0)

            print("🔥 PARSED JSON:", data)
            return data

    except Exception as e:
        print("🔥 JSON FEJL:", str(e))

    return {"name": "unknown", "price": 0, "reason": ""}


# ---------- API ----------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("🔥 ENDPOINT HIT")

    image_bytes = await file.read()
    print("🔥 FILE RECEIVED:", len(image_bytes), "bytes")

    ai_response = analyze_image_with_ai(image_bytes)
    data = extract_json(ai_response)

    print("🔥 FINAL OUTPUT:", data)

    return {
        "description": data.get("name", "unknown"),
        "price": data.get("price", 0),
        "reason": data.get("reason", "")
    }


# ---------- TEST ----------
@app.get("/")
def root():
    return {"status": "ok"}