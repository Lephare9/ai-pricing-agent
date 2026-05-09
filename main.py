# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if not prices:
        return []

    # få priser → behold
    if len(prices) < 4:
        return sorted(prices)

    filtered = []

    for i, price in enumerate(prices):

        # alle andre priser
        others = prices[:i] + prices[i + 1:]

        if not others:
            continue

        avg = statistics.mean(others)

        # undgå division med 0
        if avg <= 0:
            continue

        deviation = abs(price - avg) / avg

        # max 100% fra gennemsnit
        if deviation <= 1.0:
            filtered.append(price)

        else:

            print(
                f"OUTLIER REMOVED: "
                f"{price} "
                f"(avg without: {round(avg)})"
            )

    # fallback hvis filtrering bliver for hård
    if len(filtered) < 2:

        print("FILTER TOO AGGRESSIVE → USING ORIGINAL")

        return sorted(prices)

    filtered = sorted(list(set(filtered)))

    print("FILTERED:", filtered)

    return filtered