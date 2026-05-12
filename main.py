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
    }