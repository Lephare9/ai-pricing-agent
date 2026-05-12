# query_engine.py

import re
from difflib import SequenceMatcher

GOOD_TRANSLATIONS = {
    "chair": "stol",
    "armchair": "lænestol",
    "lamp": "lampe",
    "light fixture": "lampe",
    "table": "bord",
    "dining table": "spisebord",
    "bar stool": "barstol",
    "candle holder": "lysestage",
    "barrel": "vintønde",
    "cabinet": "skab",
    "bookshelf": "reol",
    "sofa": "sofa",
}

BAD_LABELS = [
    "wood",
    "hardwood",
    "plywood",
    "flooring",
    "floor",
    "room",
    "brown",
    "technology",
    "still life photography",
    "daylight",
    "daylighting",
    "wood stain",
    "varnish",
    "building material",
]

IMPORTANT_WORDS = [
    "wegner",
    "mogensen",
    "ph",
    "poulsen",
    "vintage",
    "retro",
    "teak",
    "eg",
    "læder",
]


def normalize_query(q):
    q = q.lower().strip()
    q = re.sub(r"\s+", " ", q)
    return q


def similarity(a, b):
    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def deduplicate_queries(queries):
    unique = []

    for q in queries:
        q = normalize_query(q)
        duplicate = False

        for existing in unique:
            if similarity(q, existing) > 0.82:
                duplicate = True
                break

        if not duplicate:
            unique.append(q)

    return unique


def score_query(query):
    score = 0
    words = query.split()

    for word in words:
        if word in IMPORTANT_WORDS:
            score += 2
        else:
            score += 1

    return score


def build_queries(gemini_data, vision_labels):
    queries = []

    if gemini_data:
        primary = gemini_data.get("primary_query")

        if primary:
            queries.append(primary)

        secondary = gemini_data.get(
            "secondary_queries",
            []
        )

        queries.extend(secondary)

    else:
        for label in vision_labels:
            label = label.lower()

            if label in BAD_LABELS:
                continue

            translated = GOOD_TRANSLATIONS.get(label)

            if translated:
                queries.append(translated)

    queries = deduplicate_queries(queries)

    queries = sorted(
        queries,
        key=score_query,
        reverse=True
    )

    return queries[:2]

