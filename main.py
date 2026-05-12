import os
import json
import httpx

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.generativeai as genai

from query_engine import build_queries

from search_engine import (
    DBAScraper,
    LauritzScraper,
    deduplicate_results,
)

from pricing_engine import (
    clean_prices,
    remove_outliers,
    remove_extreme_outliers,
    estimate_price,
    calculate_confidence,
)


GOOGLE_VISION_API_KEY = os.getenv(
    "GOOGLE_VISION_API_KEY"
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)


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


async def analyze_with_vision(image_url):

    url = (
        "https://vision.googleapis.com/v1/images:annotate"
        f"?key={GOOGLE_VISION_API_KEY}"
    )

    payload = {
        "requests": [
            {
                "image": {
                    "source": {
                        "imageUri": image_url
                    }
                },
                "features": [
                    {
                        "type": "LABEL_DETECTION",
                        "maxResults": 15,
                    },
                    {
                        "type": "WEB_DETECTION",
                        "maxResults": 10,
                    },
                    {
                        "type": "TEXT_DETECTION"
                    },
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=40) as client:

        response = await client.post(
            url,
            json=payload,
        )

    data = response.json()

    result = data["responses"][0]

    labels = []

    for label in result.get(
        "labelAnnotations",
        []
    ):
        labels.append(label["description"])

    return labels


def analyze_with_gemini(image_url):

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        prompt = """
Du analyserer billeder til en dansk AI-prisagent.

90% er IKKE designerobjekter.

Du må IKKE gætte designere.

Svar KUN som JSON.

{
 "title":"...",
 "category":"...",
 "materials":"...",
 "condition":"...",
 "designer":null,
 "brand":null,
 "designer_confidence":"low",
 "primary_query":"...",
 "secondary_queries":["..."]
}
"""

        response = model.generate_content(
            [
                prompt,
                {
                    "file_data": {
                        "mime_type": "image/jpeg",
                        "file_uri": image_url,
                    }
                },
            ]
        )

        text = response.text.strip()

        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        return json.loads(text)

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
async def analyze(data: AnalyzeRequest):

    vision_labels = await analyze_with_vision(
        data.image_url
    )

    gemini_data = analyze_with_gemini(
        data.image_url
    )

    print("VISION:", vision_labels)
    print("GEMINI:", gemini_data)

    queries = build_queries(
        gemini_data,
        vision_labels,
    )

    print("QUERIES:", queries)

    if not queries:

        return {
            "success": False,
            "error": "Ingen relevante søgninger fundet",
            "vision_labels": vision_labels,
        }

    dba = DBAScraper()
    lauritz = LauritzScraper()

    all_results = []

    use_lauritz = False

    if gemini_data:

        if (
            gemini_data.get(
                "designer_confidence"
            ) == "high"
        ):
            use_lauritz = True

        if gemini_data.get("brand"):
            use_lauritz = True

    for query in queries:

        dba_results = await dba.search(query)

        print(
            "DBA",
            query,
            len(dba_results)
        )

        all_results.extend(dba_results)

        if use_lauritz:

            lauritz_results = await lauritz.search(query)

            print(
                "Lauritz",
                query,
                len(lauritz_results)
            )

            all_results.extend(lauritz_results)

    all_results = deduplicate_results(
        all_results
    )

    prices = clean_prices(all_results)

    prices = remove_outliers(prices)

    prices = remove_extreme_outliers(prices)

    pricing = estimate_price(prices)

    confidence = calculate_confidence(prices)

    return {
        "success": True,

        "title": (
            gemini_data.get("title")
            if gemini_data
            else (
                queries[0]
                if queries
                else "Ukendt objekt"
            )
        ),

        "category": (
            gemini_data.get("category")
            if gemini_data
            else None
        ),

        "materials": (
            gemini_data.get("materials")
            if gemini_data
            else None
        ),

        "condition": (
            gemini_data.get("condition")
            if gemini_data
            else None
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

        "confidence": confidence,

        "count": len(prices),

        "queries": queries,

        "results": all_results[:12],
    }