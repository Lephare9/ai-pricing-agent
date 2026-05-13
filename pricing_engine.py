def calculate_price(results):

    if not results:

        return {
            "estimated": None,
            "low": None,
            "high": None,
            "confidence": "low",
        }

    prices = []

    for item in results:

        price = item.get("price")

        if isinstance(price, int):
            prices.append(price)

    if not prices:

        return {
            "estimated": None,
            "low": None,
            "high": None,
            "confidence": "low",
        }

    prices.sort()

    # trim outliers
    if len(prices) >= 6:
        prices = prices[1:-1]

    avg = int(
        sum(prices) / len(prices)
    )

    low = min(prices)

    high = max(prices)

    confidence = "medium"

    if len(prices) >= 8:
        confidence = "high"

    return {
        "estimated": avg,
        "low": low,
        "high": high,
        "confidence": confidence,
    }