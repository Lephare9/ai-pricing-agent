from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai

import requests
import os
import json

from pricing_engine import calculate_price
from query_engine import build_queries
from search_engine import search_dba


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)


model = genai.GenerativeModel(
    "gemini-2.5-flash"
)


@app.get("/")
async def root():

    return {
        "status": "running"
    }


async def analyze_with_gemini(image_url):

    prompt = """

Analyze this used item photo.

Return ONLY valid JSON.

{
  "title": "",
  "category": "",
  "materials": "",
  "condition": "",
  "designer": null,
  "brand": null,
  "designer_confidence": "low",
  "primary_query": "",
  "secondary_queries": []
}

Focus on Danish used marketplace search terms.

IMPORTANT:

Search queries must focus on:
- product type
- brand
- designer
- model

Avoid:
- colors
- aesthetic words
- decorative words
- material-heavy descriptions

DO NOT use words like:
- sort
- beige
- hvid
- blå
- grøn
- flot
- moderne
- dekorativ
- vintage
- retro
- rustik

Never use single-word queries.

Good examples:
- hay pc portable lampe
- kartell cindy lampe
- formspændt skolestol
- rattan lænestol
- ddsf ølkasse

Bad examples:
- sort stol
- beige drejestol
- moderne lampe
- vintage stol

"""

    image_bytes = requests.get(
        image_url
    ).content

    response = model.generate_content([

        prompt,

        {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }

    ])

    text = response.text.strip()

    text = text.replace(
        "```json",
        ""
    )

    text = text.replace(
        "```",
        ""
    )

    data = json.loads(text)

    print("")
    print("===================")
    print("GEMINI:")
    print(data)
    print("===================")

    return data


@app.post("/analyze")
async def analyze(request: Request):

    try:

        body = await request.json()

        image_url = body.get(
            "image_url"
        )

        if not image_url:

            return {
                "error": "No image_url"
            }

        gemini_data = await analyze_with_gemini(
            image_url
        )

        queries = build_queries(
            gemini_data
        )

        print("")
        print("===================")
        print("FINAL QUERIES:")
        print(queries)
        print("===================")

        all_results = []

        query_used = None

        for query in queries:

            results = await search_dba(query)

            if results:

                all_results = results
                query_used = query

                print("")
                print("===================")
                print("GOOD MATCHES USING:")
                print(query)
                print("===================")

                break

        pricing = calculate_price(
            all_results,
            query_used or ""
        )

        print("")
        print("===================")
        print("PRICING DATA:")
        print(pricing)
        print("===================")

        estimated_price = pricing.get(
            "estimated"
        )

        if estimated_price:

            estimated_price = round(
                estimated_price / 5
            ) * 5

        response = {

            "title":
                gemini_data.get("title"),

            "category":
                gemini_data.get("category"),

            "materials":
                gemini_data.get("materials"),

            "condition":
                gemini_data.get("condition"),

            "designer":
                gemini_data.get("designer"),

            "brand":
                gemini_data.get("brand"),

            "estimated_price":
                estimated_price,

            "query_used":
                query_used,

            "role":
                "shop"
        }

        print("")
        print("===================")
        print("FINAL RESPONSE:")
        print(response)
        print("===================")

        return response

    except Exception as e:

        print("")
        print("===================")
        print("ERROR:")
        print(str(e))
        print("===================")

        return {
            "error": str(e)
        }