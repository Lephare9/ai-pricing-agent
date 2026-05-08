# main.py

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
import io
import re
import json
import base64
import statistics
import requests

from PIL import Image
import google.generativeai as genai

# =====================================================

# CONFIG

# =====================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not GEMINI_API_KEY:
raise Exception("Missing GEMINI_API_KEY")

if not SERPAPI_KEY:
raise Exception("Missing SERPAPI_KEY")

genai.configure(api_key=GEMINI_API_KEY)

vision_model = genai.GenerativeModel("gemini-1.5-flash")
text_model = genai.GenerativeModel("gemini-1.5-flash")

# =====================================================

# FASTAPI

# =====================================================

app = FastAPI()

app.add_middleware(
CORSMiddleware,
allow_origins=["*"],
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
)

# =====================================================

# HELPERS

# =====================================================

def capitalize_text(text: str):
if not text:
return ""

```
text = text.strip()

return text[:1].upper() + text[1:]
```

def clean_title(title: str):
if not title:
return "Ukendt objekt"

```
title = title.strip()

replacements = {
    "lysestage i glas": "Bordlampe i glas",
    "tændstikæske i træ": "Trækrukke med låg",
    "dekorativ kasse": "Dekorativ trækasse",
}

lower = title.lower()

if lower in replacements:
    return replacements[lower]

return capitalize_text(title)
```

def clean_condition(condition: str):
if not condition:
return "God stand"

```
condition = condition.lower().strip()

return capitalize_text(condition)
```

def clean_material(material: str):
if not material:
return ""

```
material = material.lower().strip()

return capitalize_text(material)
```

def round_to_5(value):
return int(round(value / 5) * 5)

def filter_prices(prices):
filtered = []

```
for p in prices:
    if p < 25:
        continue

    if p > 100000:
        continue

    filtered.append(p)

if len(filtered) < 2:
    return filtered

median_price = statistics.median(filtered)

final = []

for p in filtered:
    if p < median_price * 0.35:
        continue

    if p > median_price * 2.5:
        continue

    final.append(p)

return final
```

def calculate_price_range(prices):
if not prices:
return None

```
median_price = statistics.median(prices)

low = median_price * 0.9
high = median_price * 1.1

low = round_to_5(low)
high = round_to_5(high)

if low == high:
    return f"{low} kr"

return f"{low} – {high} kr"
```

# =====================================================

# VISION ANALYSIS

# =====================================================

def analyze_image(image_bytes):
image = Image.open(io.BytesIO(image_bytes))

````
prompt = """
Du analyserer brugte møbler og interiør.

Returnér JSON:

{
  "title": "kort præcis titel",
  "material": "materiale",
  "condition": "kort tilstand",
  "designer": "designer hvis meget sikker ellers tom"
}

Regler:
- skriv kort
- ingen forklaringer
- dansk
- undgå hallucinationer
- hvis designer er usikker returner tom streng
- hvis objekt er lampe så skriv lampe
- hvis objekt er krukke så skriv krukke
- hvis objekt er kasse så skriv kasse
"""

response = vision_model.generate_content([
    prompt,
    image
])

text = response.text.strip()

text = text.replace("```json", "")
text = text.replace("```", "")

try:
    data = json.loads(text)
except:
    data = {
        "title": "Ukendt objekt",
        "material": "",
        "condition": "God stand",
        "designer": ""
    }

return data
````

# =====================================================

# QUERY ENRICHMENT

# =====================================================

def generate_search_queries(title, material, designer):
base = f"{title} {material}".strip()

````
prompt = f'''
Lav 6 realistiske DBA/Facebook Marketplace søgninger.

Objekt:
{base}

Designer:
{designer}

Returnér KUN JSON array.

Eksempel:
[
  "Kubus By Lassen",
  "Kubus lysestage",
  "By Lassen stage"
]
'''

try:
    response = text_model.generate_content(prompt)

    text = response.text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")

    queries = json.loads(text)

    cleaned = []

    for q in queries:
        if isinstance(q, str):
            cleaned.append(q.strip())

    if len(cleaned) > 0:
        return cleaned[:6]

except Exception as e:
    print("QUERY ENRICH ERROR:", e)

fallback = [
    f"{title} brugt",
    f"{title} vintage",
    f"{material} {title}",
]

return fallback
````

# =====================================================

# SERPAPI

# =====================================================

def extract_prices(text):
matches = re.findall(r"(\d+[.,]?\d*)\s*kr", text.lower())

```
prices = []

for match in matches:
    try:
        value = int(float(match.replace(".", "").replace(",", ".")))
        prices.append(value)
    except:
        pass

return prices
```

def serp_search(query):
url = "[https://serpapi.com/search.json](https://serpapi.com/search.json)"

```
params = {
    "engine": "google",
    "q": query,
    "api_key": SERPAPI_KEY,
    "hl": "da",
    "gl": "dk",
    "num": 10,
}

try:
    response = requests.get(url, params=params, timeout=8)

    data = response.json()

    prices = []

    organic = data.get("organic_results", [])

    for result in organic:
        title = result.get("title", "")
        snippet = result.get("snippet", "")

        combined = f"{title} {snippet}"

        found = extract_prices(combined)

        prices.extend(found)

    return prices

except Exception as e:
    print("SERP ERROR:", e)
    return []
```

# =====================================================

# MAIN ANALYSIS

# =====================================================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
try:
image_bytes = await file.read()

```
    vision = analyze_image(image_bytes)

    title = clean_title(vision.get("title", ""))
    material = clean_material(vision.get("material", ""))
    condition = clean_condition(vision.get("condition", ""))
    designer = vision.get("designer", "")

    print("VISION:", vision)

    queries = generate_search_queries(
        title,
        material,
        designer
    )

    print("QUERIES:", queries)

    all_prices = []

    for q in queries:
        results = serp_search(q)

        print("QUERY:", q)
        print("RAW:", results)

        all_prices.extend(results)

    filtered_prices = filter_prices(all_prices)

    print("FILTERED:", filtered_prices)

    price_range = calculate_price_range(filtered_prices)

    response = {
        "title": title,
        "material": material,
        "condition": condition,
        "designer": designer,
        "price": price_range if price_range else "Ukendt pris",
        "found_prices": len(filtered_prices),
        "queries": queries,
        "raw_prices": filtered_prices,
    }

    return JSONResponse(response)

except Exception as e:
    print("ANALYZE ERROR:", e)

    return JSONResponse(
        {
            "error": str(e)
        },
        status_code=500
    )
```

# =====================================================

# HEALTH

# =====================================================

@app.get("/")
def root():
return {
"status": "ok"
}
