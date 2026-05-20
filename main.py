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


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(
        api_key=GEMINI_API_KEY
    )


VALID_PASSWORDS = {
    "shop456": "shop"
}


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
    password: str


async def analyze_with_gemini(image_bytes):

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

Use SHORT marketplace search queries.

Prefer:
- brand names
- designer names
- model names

Avoid:
- aesthetic descriptions
- visual descriptions
- material-heavy descriptions

Maximum 3-4 search words unless exact designer/model is known.

Good examples:
- kartell cindy lampe
- hay pc portable
- montana reol

Bad examples:
- transparent rillet plast lampe
- moderne nordisk bordlampe
- flot designer lampe
"""

        result = model.generate_content(
            [
                prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            ]
        )

        text = result.text.strip()

        if text.startswith("```json"):
            text = text.replace(
                "```json",
                ""
            )

        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(
            text.strip()
        )

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

    try:

        role = VALID_PASSWORDS.get(
            request.password
        )

        if not role:

            return {
                "error": "Unauthorized"
            }

        image_url = request.image_url

        if not image_url:

            return {
                "error": "Missing image_url"
            }

        async with httpx.AsyncClient() as client:

            response = await client.get(
                image_url,
                timeout=30
            )

            image_bytes = response.content

        gemini_data = await analyze_with_gemini(
            image_bytes
        )

        if not gemini_data:

            return {
                "error": "Gemini failed"
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

            print("===================")
            print(
                "DBA QUERY:",
                query
            )

            dba_results = await search_dba(
                query
            )

            if dba_results:

                results = dba_results

                print(
                    "GOOD MATCHES USING:",
                    query
                )

                break

        pricing_data = calculate_price(
            results
        )

        print(
            "PRICING DATA:",
            pricing_data
        )

        estimated_price = None

        if isinstance(
            pricing_data,
            dict
        ):

            estimated_price = pricing_data.get(
                "estimated"
            )

        elif isinstance(
            pricing_data,
            (int, float)
        ):

            estimated_price = pricing_data

        rounded_price = None

        if estimated_price is not None:

            rounded_price = round(
                estimated_price / 5
            ) * 5

        response_data = {

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

            "estimated_price": rounded_price,

            "query_used": queries[0]
            if queries else None,

            "role": role
        }

        print(
            "FINAL RESPONSE:",
            response_data
        )

        return response_data

    except Exception as e:

        print(
            "ERROR:",
            str(e)
        )

        return {
            "error": str(e)
        }