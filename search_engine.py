import re
import json
import httpx

from bs4 import BeautifulSoup
from difflib import SequenceMatcher

from utils import safe_int


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def normalize_title(title):

    title = title.lower()

    title = re.sub(
        r"[^a-zæøå0-9 ]",
        "",
        title
    )

    title = re.sub(r"\s+", " ", title)

    return title.strip()


def deduplicate_results(results):

    unique = []

    for item in results:

        title = normalize_title(
            item.get("title", "")
        )

        price = item.get("price")

        duplicate = False

        for existing in unique:

            existing_title = normalize_title(
                existing.get("title", "")
            )

            sim = SequenceMatcher(
                None,
                title,
                existing_title
            ).ratio()

            if (
                sim > 0.88
                and existing.get("price") == price
            ):
                duplicate = True
                break

        if not duplicate:
            unique.append(item)

        return results