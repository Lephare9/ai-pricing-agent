# ---------------------------------------------------
# BUILD PRICE
# ---------------------------------------------------

def build_price(prices):

    if not prices:
        return None

    median = statistics.median(prices)

    if median < 200:
        rounded = round(median / 10) * 10
    else:
        rounded = round(median / 50) * 50

    return int(rounded)