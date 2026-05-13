# pricing_engine.py

BAD_WORDS = [

    "campingvogn",
    "autocamper",
    "trailer",
    "leasing",
    "udlejning",
    "mpk",
    "husvogn",
    "bus",
    "varevogn",
    "bil",
]


def calculate_price(results):

    prices = []

    for item in results:

        title = (
            item.get("title", "")
            .lower()
        )

        # filtrer irrelevante annoncer væk
        skip = False

        for bad in BAD_WORDS:

            if bad in title:
                skip = True
                break

        if skip:
            continue

        price = item.get("price")

        if not isinstance(price, int):
            continue

        # basic sanity checks
        if price < 50:
            continue

        if price > 20000:
            continue

        prices.append(price)

    # ingen brugbare priser
    if len(prices) < 3:

        return {
            "estimated": None,
            "low": None,
            "high": None,
            "confidence": "low"
        }

    prices.sort()

    # fjern 2 laveste + 2 højeste
    trimmed = prices

    if len(prices) >= 6:

        trimmed = prices[2:-2]

    # fallback hvis trimmed bliver tom
    if not trimmed:

        trimmed = prices

    estimated = int(
        sum(trimmed) / len(trimmed)
    )

    low = min(trimmed)

    high = max(trimmed)

    confidence = "medium"

    if len(trimmed) >= 6:
        confidence = "high"

    return {

        "estimated": estimated,

        "low": low,

        "high": high,

        "confidence": confidence
    }