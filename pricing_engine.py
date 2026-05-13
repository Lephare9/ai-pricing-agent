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

        if price < 50:
            continue

        if price > 20000:
            continue

        prices.append(price)

    if len(prices) < 3:

        return {
            "estimated": None,
            "low": None,
            "high": None,
            "confidence": "low"
        }

    prices.sort()

    trimmed = prices

    # fjern 2 laveste + 2 højeste
    if len(prices) >= 6:

        trimmed = prices[2:-2]

    if not trimmed:

        trimmed = prices

    estimated = round(
        (
            sum(trimmed) / len(trimmed)
        ) / 5
    ) * 5

    low = min(trimmed)

    high = max(trimmed)

    confidence = "medium"

    if len(trimmed) >= 6:
        confidence = "high"

    print("")
    print("===== PRICING DEBUG =====")

    print(
        f"RAW PRICES: {prices}"
    )

    print(
        f"TRIMMED: {trimmed}"
    )

    print(
        f"ESTIMATED: {estimated}"
    )

    print("=========================")
    print("")

    return {

        "estimated": estimated,

        "low": low,

        "high": high,

        "confidence": confidence
    }