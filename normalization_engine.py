import re


NORMALIZATION_RULES = [

    # TØNDER

    {
        "contains": [
            "barrel",
        ],
        "query": "trætønde",
    },

    {
        "contains": [
            "wine barrel",
        ],
        "query": "vintønde",
    },

    {
        "contains": [
            "whiskey barrel",
        ],
        "query": "whiskyfad",
    },

    # STOLE

    {
        "contains": [
            "wicker",
            "chair",
        ],
        "query": "kurvestol",
    },

    {
        "contains": [
            "rattan",
            "chair",
        ],
        "query": "rattanstol",
    },

    {
        "contains": [
            "molded",
            "chair",
        ],
        "query": "skalstol",
    },

    {
        "contains": [
            "plywood",
            "chair",
        ],
        "query": "skalstol",
    },

    {
        "contains": [
            "metal",
            "chair",
        ],
        "query": "metalstol",
    },

    {
        "contains": [
            "wood",
            "chair",
        ],
        "query": "træstol",
    },

    {
        "contains": [
            "leather",
            "chair",
        ],
        "query": "læderstol",
    },

    # BORDE

    {
        "contains": [
            "coffee",
            "table",
        ],
        "query": "sofabord",
    },

    {
        "contains": [
            "dining",
            "table",
        ],
        "query": "spisebord",
    },

    {
        "contains": [
            "wooden",
            "table",
        ],
        "query": "træbord",
    },

    # LAMPER

    {
        "contains": [
            "floor",
            "lamp",
        ],
        "query": "gulvlampe",
    },

    {
        "contains": [
            "desk",
            "lamp",
        ],
        "query": "bordlampe",
    },

    {
        "contains": [
            "pendant",
            "light",
        ],
        "query": "pendel",
    },

    {
        "contains": [
            "metal",
            "lamp",
        ],
        "query": "metallampe",
    },

    # OPBEVARING

    {
        "contains": [
            "cabinet",
        ],
        "query": "skab",
    },

    {
        "contains": [
            "bookcase",
        ],
        "query": "bogreol",
    },

    {
        "contains": [
            "dresser",
        ],
        "query": "kommode",
    },

    {
        "contains": [
            "shelf",
        ],
        "query": "reol",
    },

    # SOFA

    {
        "contains": [
            "leather",
            "sofa",
        ],
        "query": "lædersofa",
    },

    {
        "contains": [
            "fabric",
            "sofa",
        ],
        "query": "stofsofa",
    },

    # SPEJL

    {
        "contains": [
            "mirror",
        ],
        "query": "spejl",
    },
]


BROAD_WORDS = [

    "wood",
    "metal",
    "object",
    "design",
    "furniture",
    "chair",
    "table",
    "lamp",
    "room",
    "interior",
    "home",
]


def clean_text(text):

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9æøå ]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_query(text):

    if not text:
        return None

    text = clean_text(text)

    # regelbaseret semantic mapping
    for rule in NORMALIZATION_RULES:

        matched = True

        for word in rule["contains"]:

            if word not in text:
                matched = False
                break

        if matched:

            print(
                f"NORMALIZED: {text} -> {rule['query']}"
            )

            return rule["query"]

    # fallback cleanup
    words = text.split()

    cleaned_words = []

    for word in words:

        if word in BROAD_WORDS:
            continue

        if len(word) < 3:
            continue

        cleaned_words.append(word)

    # forsøg compound
    if len(cleaned_words) >= 2:

        compound = (
            cleaned_words[0]
            + cleaned_words[1]
        )

        return compound

    # enkeltord fallback
    if cleaned_words:

        return cleaned_words[0]

    return None