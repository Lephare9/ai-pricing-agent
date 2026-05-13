import re

from difflib import SequenceMatcher


GOOD_TRANSLATIONS = {

    "chair": "stol",
    "armchair": "lænestol",
    "table": "bord",
    "lamp": "lampe",
    "light fixture": "lampe",
    "sofa": "sofa",
    "wood": "træ",
    "metal": "metal",
    "iron": "metal",
    "steel": "metal",
    "leather": "læder",
    "teak": "teak",
    "oak": "eg",
    "rattan": "flet",
    "wicker": "kurv",
    "barrel": "vintønde",
    "keg": "vintønde",
}


BAD_LABELS = [

    "technology",
    "electronic device",
    "gadget",
    "communication device",
    "mobile phone",
    "smartphone",
    "graphics",
    "font",
    "text",
    "room",
    "design",
    "creative arts",
    "symmetry",
    "pattern",
    "triangle",
    "wood stain",
    "varnish",
    "hardwood",
    "plywood",
    "brown",
    "black",
    "grey",
    "silver",
]


IMPORTANT_WORDS = [

    "wegner",
    "mogensen",
    "ph",
    "poulsen",
    "teak",
    "læder",
    "flet",
    "metal",
    "skal",
    "retro",
    "vintage",
]


BAD_QUERY_WORDS = [

    "sort",
    "sorte",
    "hvid",
    "brun",
    "grå",
    "grey",
    "silver",
    "black",
    "brown",
    "modern",
    "moderne",
]


def normalize_query(q):

    q = q.lower().strip()

    q = re.sub(
        r"\s+",
        " ",
        q
    )

    return q


def simplify_query(query):

    words = query.lower().split()

    cleaned = []

    for word in words:

        if word not in BAD_QUERY_WORDS:
            cleaned.append(word)

    return " ".join(cleaned)


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


def build_queries(
    gemini_data,
    vision_labels,
    web_entities,
):

    queries = []

    if gemini_data:

        primary = gemini_data.get(
            "primary_query"
        )

        if primary:
            queries.append(primary)

        secondary = gemini_data.get(
            "secondary_queries",
            []
        )

        queries.extend(secondary)

    for entity in web_entities:

        entity = entity.lower()

        if len(entity) < 3:
            continue

        queries.append(entity)

    for label in vision_labels:

        label = label.lower()

        if label in BAD_LABELS:
            continue

        translated = GOOD_TRANSLATIONS.get(label)

        if translated:
            queries.append(translated)

    queries = [
        simplify_query(q)
        for q in queries
    ]

    queries = [
        q for q in queries
        if q.strip()
    ]

    queries = deduplicate_queries(
        queries
    )

    queries = sorted(
        queries,
        key=score_query,
        reverse=True
    )

    return queries[:4]