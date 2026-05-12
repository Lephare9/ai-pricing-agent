import statistics
import numpy as np


def clean_prices(results):

    prices = []

    for item in results:

        price = item.get("price")

        if not price:
            continue

        if price <= 0:
            continue

        if price > 500000:
            continue

        prices.append(price)

    return prices


def remove_outliers(prices):

    if len(prices) < 4:
        return prices

    q1 = np.percentile(prices, 25)
    q3 = np.percentile(prices, 75)

    iqr = q3 - q1

    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr

    return [
        p for p in prices
        if low <= p <= high
    ]


def remove_extreme_outliers(prices):

    if len(prices) < 6:
        return prices

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        if p > median * 4:
            continue

        if p < median * 0.25:
            continue

        filtered.append(p)

    return filtered


def estimate_price(prices):

    if not prices:

        return {
    return "Lav"