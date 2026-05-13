import os
import json
import base64
import httpx

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.generativeai as genai

from fallback_engine import build_queries
from normalization_engine import normalize_query
from pricing_engine import calculate_price
from search_engine import search_dba


GOOGLE_VISION_API_KEY = os.getenv(
    "GOOGLE_VISION_API_KEY"
)

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


async def analyze_with_vision(image_url):

    if not GOOGLE_VISION_API_KEY:
        return []

    try:

        image_response = httpx.get(
            image_url,
            timeout=20
        )

        image_base64 = base64.b64encode(
            image_response.content
        ).decode("utf-8")

        url = (
            "https://vision.googleapis.com/v1/"
            f"images:annotate?key={GOOGLE_VISION_API_KEY}"
        )

        payload = {

            "requests": [

                {

                    "image": {
                        "content": image_base64
                    },

                    "features": [

                        {
                            "type": "LABEL_DETECTION",
                            "maxResults": 15
                        },

                        {
                            "type": "WEB_DETECTION",
                            "maxResults": 10
                        }
                    ]
                }
            ]
        }

        async with httpx.AsyncClient(
            timeout=30
        ) as client:

            response = await client.post(
                url,
                json=payload
            )

        data = response.json()

        labels = []

        responses = data.get(
            "responses",
            []
        )

        if not responses:
            return []

        first = responses[0]

        label_annotations = first.get(
            "labelAnnotations",
            []
        )

        for item in label_annotations:

            desc = item.get(
                "description"
            )

            if desc:
                labels.append(desc)

        web_detection = first.get(
            "webDetection",
            {}
        )

        web_entities = web_detection.get(
            "webEntities",
            []
        )

        for entity in web_entities:

            desc = entity.get(
                "description"
            )

            if desc and desc not in labels:

                labels.append(desc)

        return labels

    except Exception as e:

        print(
            f"VISION ERROR: {e}"
        )

        return []


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
        """

        result = model.generate_content(
            [
                prompt,
                {
                    "mime_type": "image/jpeg",
                    "data": httpx.get(
                        image_url
                    ).content
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

    vision_labels = await analyze_with_vision(
        data.image_url
    )

    print(
        f"VISION: {vision_labels}"
    )

    gemini_data = await analyze_with_gemini(
        data.image_url
    )

    print(
        f"GEMINI: {gemini_data}"
    )

    queries = []

    # GEMINI QUERY
    if gemini_data:

        primary = gemini_data.get(
            "primary_query"
        )

        if primary:

            normalized = normalize_query(
                primary
            )

            if normalized:
                queries.append(normalized)

            else:
                queries.append(primary)

    # FALLBACK
    if not queries:

        queries = build_queries(
            vision_labels
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

        # hvis gode hits:
        # stop her
        if len(dba_results) >= 8:

            final_results = dba_results

            print(
                f"GOOD MATCHES USING: {query}"
            )

            break

        # fallback hvis få hits
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

        "count": len(final_results),

        "queries": queries,

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

        "results": [

            {
                "title": r.get("title"),
                "price": r.get("price"),
            }

            for r in final_results
        ]
    }