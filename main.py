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
            "..."
          ]
        }

        IMPORTANT:
        - Focus on Danish DBA marketplace wording
        - Use SHORT search queries
        - Prefer ONE strong DBA query
        - Avoid long descriptions
        - Avoid unnecessary colors
        - Avoid generic filler words
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

        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        parsed = json.loads(text)

        return parsed

    except Exception as e:

        print(
            f"GEMINI ERROR: {e}"
        )

        return None


@app.get("/")
async def root():

    return {
        "status": "ok"
    }


@app.post("/analyze")
async def analyze(data: AnalyzeRequest):

    try:

        print("")
        print("===================")
        print("")

        print(
            f"IMAGE URL: {data.image_url}"
        )

        image_response = httpx.get(
            data.image_url,
            timeout=30
        )

        image_bytes = image_response.content

        print(
            f"IMAGE SIZE: {len(image_bytes)} bytes"
        )

    except Exception as e:

        print(
            f"IMAGE DOWNLOAD ERROR: {e}"
        )

        return {
            "success": False,
            "error": "Kunne ikke hente billede"
        }

    # VISION HELT FJERNET
    print(
        "VISION DISABLED"
    )

    gemini_data = await analyze_with_gemini(
        image_bytes
    )

    print(
        f"GEMINI: {gemini_data}"
    )

    if not gemini_data:

        return {
            "success": False,
            "error": "Gemini analyse fejlede"
        }

    queries = build_queries(
        gemini_data
    )

    print(
        f"QUERIES: {queries}"
    )

    all_results = []

    for query in queries:

        print("")
        print("===================")
        print("")

        print(
            f"DBA QUERY: {query}"
        )

        dba_results = await search_dba(
            query
        )

        print(
            f"DBA {query} {len(dba_results)}"
        )

        all_results.extend(
            dba_results
        )

    # dedupe
    deduped = []

    seen = set()

    for item in all_results:

        key = (
            item.get("title"),
            item.get("price")
        )

        if key in seen:
            continue

        seen.add(key)

        deduped.append(item)

    all_results = deduped[:10]

    pricing = calculate_price(
        all_results
    )

    print(
        f"FINAL PRICE: {pricing}"
    )

    return {

        "success": True,

        "title": gemini_data.get(
            "title",
            "Ukendt produkt"
        ),

        "estimated_price": pricing.get(
            "estimated"
        ),

        "price_low": pricing.get(
            "low"
        ),

        "price_high": pricing.get(
            "high"
        ),

        "confidence": pricing.get(
            "confidence"
        ),

        "count": len(all_results),

        "queries": queries,

        "materials": gemini_data.get(
            "materials"
        ),

        "condition": gemini_data.get(
            "condition"
        ),

        "results": all_results
    }