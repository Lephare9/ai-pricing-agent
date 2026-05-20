from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai

import requests
import os
import json
import re

from pricing_engine import calculate_price


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


NEGATIVE_CONTEXT = [

    "mønt",
    "møntsæt",
    "krugerrand",
    "pokemon",
    "lego",
    "frimærke",
    "grillbestik",
    "mælketænder",
    "investering",
    "guldbarre",
    "sølvmønt",
    "samling",
    "medalje"
]


GENERIC_WORDS = [

    "moderne",
    "dekorativ",
    "patineret",
    "vintage",
    "flot",
    "smuk",
    "unik",
    "messing",
    "metal",
    "træ",
    "kunst",
    "figur"
]


@app.get("/")
async def root():

    return {
        "status": "running"
    }


def clean_text(text):

    if not text:
        return ""

    return str(text).lower().strip()


def is_relevant_result(title):

    title_lower = clean_text(title)

    for word in NEGATIVE_CONTEXT:

        if word in title_lower:
            return False

    return True


def simplify_query(query):

    words = query.lower().split()

    important = [

        w for w in words

        if w not in GENERIC_WORDS
    ]

    if not important:
        return query

    return " ".join(
        important[:2]
    )


def search_dba(query):

    try:

        print("===================")
        print("DBA QUERY:", query)

        url = "https://www.dba.dk/soeg/"

        params = {
            "soeg": query
        }

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        print(
            "DBA STATUS:",
            response.status_code
        )

        html = response.text

        matches = re.findall(

            r'(\d[\d\.]*)\s*kr\..{0,220}',

            html,

            re.IGNORECASE
        )

        raw_count = len(matches)

        results = []

        # only inspect first relevant block

        for match in matches[:20]:

            text = match.strip()

            price_match = re.search(
                r'(\d[\d\.]*)\s*kr',
                text
            )

            if not price_match:
                continue

            price = price_match.group(1)

            price = price.replace(".", "")

            try:

                price_int = int(price)

            except:
                continue

            # unrealistic

            if (
                price_int < 25
                or
                price_int > 25000
            ):
                continue

            # semantic blacklist

            if not is_relevant_result(text):
                continue

            results.append({

                "title": text,

                "price": price_int
            })

            # early stop

            if len(results) >= 8:
                break

        print(
            "DBA RESULTS:",
            raw_count
        )

        print(
            "DBA CLEAN RESULTS:",
            len(results)
        )

        return results

    except Exception as e:

        print(
            "DBA ERROR:",
            str(e)
        )

        return []


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

Use SHORT marketplace search queries.

Prefer:
- brand names
- designer names
- model names

Avoid:
- aesthetic descriptions
- visual descriptions
- material-heavy descriptions

Never use single-word search queries.

Avoid generic object names like:
- lampe
- stol
- trææske
- bord
- skål

Always include:
- style
- shape
- object type
or brand/designer if known.

Avoid broad collectible-related wording.

Good examples:
- kartell cindy lampe
- hay pc portable
- beige drejelænestol
- trææske mønster
- vindmølle figur

Bad examples:
- lampe
- stol
- trææske
- moderne designer lampe
- transparent plast lampe

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

    print("GEMINI:", data)

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

        queries = []

        primary_query = gemini_data.get(
            "primary_query"
        )

        if primary_query:
            queries.append(primary_query)

        for q in gemini_data.get(
            "secondary_queries",
            []
        ):

            if q not in queries:
                queries.append(q)

        print("QUERIES:", queries)

        all_results = []

        query_used = None

        for query in queries:

            results = search_dba(query)

            # fallback:
            # broaden search automatically

            if not results:

                simple_query = simplify_query(
                    query
                )

                print(
                    "FALLBACK QUERY:",
                    simple_query
                )

                results = search_dba(
                    simple_query
                )

            if results:

                all_results = results

                query_used = query

                print(
                    "GOOD MATCHES USING:",
                    query
                )

                break

        pricing = calculate_price(
            all_results,
            query_used or ""
        )

        print(
            "PRICING DATA:",
            pricing
        )

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

        print(
            "FINAL RESPONSE:",
            response
        )

        return response

    except Exception as e:

        print(
            "ERROR:",
            str(e)
        )

        return {
            "error": str(e)
        }