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

    return queries[:2]