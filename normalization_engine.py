import re


STOPWORDS = {

    # GENEREL STØJ
    "vintage",
    "moderne",
    "flot",
    "smuk",
    "fed",
    "retro",
    "klassisk",
    "stil",
    "design",

    # FARVER
    "sort",
    "hvid",
    "grå",
    "graa",
    "mørk",
    "mørkeblå",
    "mørkebla",
    "blå",
    "bla",
    "lysegrå",
    "lysegraa",
    "beige",
    "brun",
    "sølv",
    "solv",
    "krom",

    # STØJ FRA GEMINI
    "med",
    "som",
    "til",
    "for",
    "og",
    "the",

    # MATERIALER SOM OFTE FORSTYRRER
    "metal",
    "plast",
    "plastic"
}


IMPORTANT_WORDS = {

    # MØBLER
    "sofa",
    "lænestol",
    "laenestol",
    "stol",
    "skalstol",
    "kurvestol",
    "bord",
    "spisebord",
    "reol",
    "kommode",

    # LAMPER
    "lampe",
    "bordlampe",
    "gulvlampe",
    "pendel",

    # VVS
    "armatur",
    "vandhane",
    "blandingsbatteri",

    # MATERIALER SOM ER VIGTIGE
    "keramik",
    "træ",
    "trae",
    "rattan",
    "flet",

    # BRANDS
    "grohe",
    "ikea",
    "hay",
    "fritz",
    "hans",
    "wegner"
}


def normalize_query(text):

    if not text:
        return ""

    text = text.lower()

    text = text.replace(",", " ")

    words = re.findall(
        r"\w+",
        text
    )

    cleaned = []

    for word in words:

        if len(word) < 3:
            continue

        # behold vigtige ord
        if word in IMPORTANT_WORDS:

            if word not in cleaned:
                cleaned.append(word)

            continue

        # fjern støj
        if word in STOPWORDS:
            continue

        # skip tal
        if word.isdigit():
            continue

        # skip meget lange mærkelige ord
        if len(word) > 24:
            continue

        cleaned.append(word)

    # DBA fungerer bedst med få ord
    cleaned = cleaned[:4]

    # DUPLIKATFILTER
    final = []

    seen = set()

    for word in cleaned:

        if word in seen:
            continue

        seen.add(word)

        final.append(word)

    # SPECIAL CASES

    # kurv + stol => kurvestol
    if "kurv" in final and "stol" in final:

        final = [
            x for x in final
            if x not in ["kurv", "stol"]
        ]

        final.insert(
            0,
            "kurvestol"
        )

    # keramik + lampe
    if "keramik" in final and "bordlampe" in final:

        return "keramik bordlampe"

    # grohe + blandingsbatteri
    if (
        "grohe" in final
        and "blandingsbatteri" in final
    ):

        return "grohe blandingsbatteri"

    # sofa prioritet
    if "sofa" in final:

        important = []

        for word in final:

            if word in [
                "sofa",
                "lænestol",
                "laenestol",
                "rattan",
                "flet",
                "træ",
                "trae"
            ]:

                important.append(word)

        if important:
            return " ".join(
                important[:3]
            )

    return " ".join(final[:4])