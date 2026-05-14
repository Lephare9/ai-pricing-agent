import os
import json
import httpx

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.generativeai as genai

from query_engine import build_queries
from pricing_engine import calculate_price
from search_engine import search_dba


GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

if GEMINI_API_KEY:

    genai.configure(
        api_key=GEMINI_API_KEY
    )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):

    image_url: str


async def analyze_with_gemini(image_url):

    if not GEMINI_API_KEY:
        return None

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        prompt = """
Analyze this used item photo.

Return ONLY valid JSON.

{
    "title": "...",
    "category": "...",
    "materials": "...",
    "condition": "...",
    "designer": null,
    "brand": null,
    "designer_confidence": "low",
    "primary_query": "...",
    "secondary_queries": [
        "...",
        "..."
    ]
}

Focus on Danish used marketplace search terms.

Keep titles realistic and short.

IMPORTANT:
Queries should match how normal people search on DBA.

Prefer:
- tripod gulvlampe
- teak kommode
- marokkansk læderpuf
- læderjakke biker

Avoid overly generic queries like:
- lampe
- stol
- jakke

Avoid overly detailed descriptions.
"""

        async with httpx.AsyncClient() as client:

            response = await client.get(
                image_url,
                timeout=30
            )

            image_bytes = response.content

        result = model.generate_content(
            [
                prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]
        )

        text = (
            result.text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        data = json.loads(text)

        print(
            "GEMINI:",
            data
        )

        return data

    except Exception as e:

        print(
            "GEMINI ERROR:",
            str(e)
        )

        return None


@app.get("/")
async def root():

    return {
        "status": "running"
    }


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):

    gemini_data = await analyze_with_gemini(
        request.image_url
    )

    if not gemini_data:

        return {
            "success": False
        }

    queries = build_queries(
        gemini_data
    )

    print(
        "QUERIES:",
        queries
    )

    results = []

    for query in queries:

        search_results = await search_dba(
            query
        )

        if search_results:

            results = search_results

            print(
                f"GOOD MATCHES USING: {query}"
            )

            break

    if not results:

        rounded_price = None

    else:

        estimated_price = calculate_price(
            results
        )

        if estimated_price:

            rounded_price = round(
                estimated_price / 5
            ) * 5

        else:

            rounded_price = None

    return {
        "success": True,
        "title": gemini_data.get(
            "title"
        ),
        "category": gemini_data.get(
            "category"
        ),
        "materials": gemini_data.get(
            "materials"
        ),
        "condition": gemini_data.get(
            "condition"
        ),
        "designer": gemini_data.get(
            "designer"
        ),
        "brand": gemini_data.get(
            "brand"
        ),
        "price": rounded_price,
        "query_used": queries[0]
        if queries else None
    }