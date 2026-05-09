# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if not prices:
        return []

    # få priser → behold alt
    if len(prices) < 4:
        return sorted(prices)

    # brug median i stedet for gennemsnit
    med = statistics.median(prices)

    # sikkerhed
    if med <= 0:
        return sorted(prices)

    filtered = []

    for price in prices:

        deviation = abs(price - med) / med

        # max 100% fra median
        if deviation <= 1.0:

            filtered.append(price)

        else:

            print(
                f"OUTLIER REMOVED: "
                f"{price} "
                f"(median: {round(med)})"
            )

    # hvis filtrering bliver for hård
    if len(filtered) < 2:

        print("FILTER TOO AGGRESSIVE → USING ORIGINAL")

        return sorted(prices)

    filtered = sorted(list(set(filtered)))

    print("FILTERED:", filtered)

    return filtered