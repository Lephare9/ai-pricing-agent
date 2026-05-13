import os
import json

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai

from query_engine import optimize_query
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


# TEMP:
# Vision disabled
ENABLE_VISION = False


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
async def analyze(
    file: UploadFile = File(...)
):

    image_bytes = await file.read()

    print("")
    print("===================")
    print("VISION DISABLED")
    print("===================")

    gemini_data = await analyze_with_gemini(
        image_bytes
    )

    print(
        f"GEMINI: {gemini_data}"
    )

    queries = optimize_query(
        gemini_data
    )

    # CLEANUP

    cleaned_queries = []

    seen = set()

    for q in queries:

        q = q.strip().lower()

        if len(q) < 2:
            continue

        if q in seen:
            continue

        seen.add(q)

        cleaned_queries.append(q)

    queries = cleaned_queries[:3]

    print("")
    print("===================")

    print(
        f"QUERIES: {queries}"
    )

    final_results = []

    # CASCADING SEARCH

    for query in queries:

        print("")
        print("===================")

        dba_results = await search_dba(
            query
        )

        print(
            f"DBA {query} {len(dba_results)}"
        )

        # GOOD MATCH
        # stop after first good query

        if len(dba_results) >= 5:

            final_results = dba_results

            print(
                f"GOOD MATCHES USING: {query}"
            )

            break

        # fallback

        if not final_results:
            final_results = dba_results

    # FINAL DEDUPE

    deduped = []

    seen = set()

    for item in final_results:

        key = (
            item.get("title"),
            item.get("price")
        )

        if key in seen:
            continue

        seen.add(key)

        deduped.append(item)

    final_results = deduped[:10]

    pricing = calculate_price(
        final_results
    )

    print("")
    print("===================")

    print(
        f"FINAL RESULTS: {len(final_results)}"
    )

    print("===================")
    print("")

    return {

        "success": True,

        "title": (
            gemini_data.get("title")
            if gemini_data
            else (
                queries[0]
                if queries
                else "Ukendt produkt"
            )
        ),

        "estimated_price": pricing[
            "estimated"
        ],

        "price_low": pricing[
            "low"
        ],

        "price_high": pricing[
            "high"
        ],

        "confidence": pricing[
            "confidence"
        ],

        "materials": (
            gemini_data.get("materials")
            if gemini_data
            else None
        ),

        "condition": (
            gemini_data.get("condition")
            if gemini_data
            else None
        )
    }