import re


REMOVE_WORDS = {

    # colors

    "sort",
    "beige",
    "hvid",
    "grøn",
    "gron",
    "blå",
    "bla",
    "gul",
    "rød",
    "rod",
    "brun",
    "grå",
    "gra",
    "mørk",
    "lys",
    "naturfarvet",

    # aesthetic

    "vintage",
    "retro",
    "moderne",
    "dekorativ",
    "rustik",
    "smuk",
    "unik",
    "flot",
    "patineret",

    # materials

    "metal",
    "træ",
    "trae",
    "messing",
    "glas",
    "plast",

    # noise

    "god",
    "stand",
    "brugt"
}


OBJECT_NORMALIZATION = {

    "drejestol": "lænestol",
    "drejelænestol": "lænestol",

    "pendellampe": "lampe",
    "bordlampe": "lampe",
    "gulvlampe": "lampe",

    "kurvestol": "lænestol",
    "fletstol": "lænestol",

    "skolestol": "stol",
    "kantinestol": "stol",
}


def clean_query(text):

    if not text:
        return ""

    text = text.lower()

    words = re.findall(
        r'\w+',
        text
    )

    cleaned = []

    for word in words:

        if word in REMOVE_WORDS:
            continue

        word = OBJECT_NORMALIZATION.get(
            word,
            word
        )

        cleaned.append(word)

    # dedupe

    final_words = []

    for word in cleaned:

        if word not in final_words:
            final_words.append(word)

    return " ".join(
        final_words
    ).strip()


def build_queries(gemini_data):

    queries = []

    primary = gemini_data.get(
        "primary_query",
        ""
    )

    secondary = gemini_data.get(
        "secondary_queries",
        []
    )

    all_queries = [primary] + secondary

    for q in all_queries:

        cleaned = clean_query(q)

        if not cleaned:
            continue

        if len(cleaned.split()) < 2:
            continue

        if cleaned not in queries:
            queries.append(cleaned)

    # fallback

    title = gemini_data.get(
        "title",
        ""
    )

    cleaned_title = clean_query(title)

    if (
        cleaned_title
        and
        cleaned_title not in queries
        and
        len(cleaned_title.split()) >= 2
    ):

        queries.append(
            cleaned_title
        )

    return queries[:6]