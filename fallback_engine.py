import re


IGNORE_LABELS = [
    "still life photography",
    "indoor",
    "room",
    "design",
    "furniture",
    "photography",
    "wood stain",
    "hardwood",
    "plywood",
    "floor",
    "flooring",
    "interior design",
    "home accessory",
    "grey",
    "black",
    "white",
    "brown",
    "rectangle",
    "material",
    "natural material",
]


OBJECT_MAP = {
    "chair": "stol",
    "armrest": "lænestol",
    "table": "bord",
    "lamp": "lampe",
    "sofa": "sofa",
    "cabinet": "skab",
    "shelf": "reol",
    "mirror": "spejl",
    "barrel": "vintønde",
    "bench": "bænk",
}


MATERIAL_MAP = {
    "wicker": "kurv",
    "rattan": "rattan",
    "wood": "træ",
    "metal": "metal",
    "steel": "metal",
    "iron": "metal",
    "leather": "læder",
    "plastic": "plast",
    "glass": "glas",
    "fabric": "stof",
    "textile": "stof",
}


COMPOUND_RULES = [
    {
        "contains": ["wicker", "chair"],
        "queries": [
            "kurvestol",
            "rattanstol",
            "fletstol",
        ],
    },
    {
        "contains": ["rattan", "chair"],
        "queries": [
            "rattanstol",
            "kurvestol",
        ],
    },
    {
        "contains": ["metal", "chair"],
        "queries": [
            "metalstol",
            "spisebordsstol",
        ],
    },
    {
        "contains": ["wood", "chair"],
        "queries": [
            "træstol",
            "spisebordsstol",
        ],
    },
    {
        "contains": ["leather", "chair"],
        "queries": [
            "læderstol",
            "lænestol",
        ],
    },
    {
        "contains": ["wood", "table"],
        "queries": [
            "træbord",
            "sofabord",
        ],
    },
    {
        "contains": ["metal", "lamp"],
        "queries": [
            "metallampe",
            "bordlampe",
        ],
    },
]


def normalize_label(label):
    return label.strip().lower()


def clean_labels(labels):

    cleaned = []

    for label in labels:

        l = normalize_label(label)

        if l in IGNORE_LABELS:
            continue

        cleaned.append(l)

    return cleaned


def build_queries(labels):

    labels = clean_labels(labels)

    queries = []

    # compound rules først
    for rule in COMPOUND_RULES:

        matched = True

        for needed in rule["contains"]:
            if needed not in labels:
                matched = False
                break

        if matched:
            queries.extend(rule["queries"])

    # material + object fallback
    found_objects = []
    found_materials = []

    for label in labels:

        if label in OBJECT_MAP:
            found_objects.append(
                OBJECT_MAP[label]
            )

        if label in MATERIAL_MAP:
            found_materials.append(
                MATERIAL_MAP[label]
            )

    for material in found_materials:
        for obj in found_objects:

            compound = f"{material}{obj}"

            if len(compound) > 5:
                queries.append(compound)

    # simple object fallback
    queries.extend(found_objects)

    # remove duplicates
    final_queries = []

    seen = set()

    for q in queries:

        q = q.strip().lower()

        q = re.sub(r"\s+", " ", q)

        if q and q not in seen:
            seen.add(q)
            final_queries.append(q)

    return final_queries[:5]