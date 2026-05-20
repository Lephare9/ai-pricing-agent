import re
import statistics


def extract_price(text):

    if not text:
        return None

    text = str(text).lower()

    text = text.replace(".", "")
    text = text.replace(",", "")

    matches = re.findall(
        r'(\d{2,6})\s*kr',
        text
    )

    if not matches:

        matches = re.findall(
            r'\b(\d{2,6})\b',
            text
        )

    for match in matches:

        try:

            price = int(match)

            if 25 <= price <= 200000:
                return price

        except:
            pass

    return None


def calculate_price(results):

    try:

        prices = []

        for item in results:

            price = None

            if isinstance(item, dict):

                price = extract_price(
                    item.get("price")
                )

                if not price:

                    price = extract_price(
                        item.get("title")
                    )

            else:

                price = extract_price(
                    str(item)
                )

            if price:
                prices.append(price)

        prices = sorted(prices)

        print("===== PRICING DEBUG =====")
        print("RAW PRICES:", prices)

        if not prices:

            print("NO PRICES FOUND")
            print("=========================")

            return {
                "estimated": None,
                "low": None,
                "high": None,
                "confidence": "low"
            }

        # FEW RESULTS
        # use average directly

        if len(prices) <= 6:

            estimated = round(
                sum(prices) / len(prices)
            )

            print(
                "FEW RESULTS MODE"
            )

            print(
                "ESTIMATED:",
                estimated
            )

            print("=========================")

            return {
                "estimated": estimated,
                "low": min(prices),
                "high": max(prices),
                "confidence": "low"
            }

        # MANY RESULTS
        # aggressive top trimming

        q1 = statistics.quantiles(
            prices,
            n=4
        )[0]

        q3 = statistics.quantiles(
            prices,
            n=4
        )[2]

        iqr = q3 - q1

        lower_bound = q1 - (
            1.5 * iqr
        )

        upper_bound = q3 + (
            0.45 * iqr
        )

        trimmed = [

            p for p in prices

            if (
                p >= lower_bound
                and
                p <= upper_bound
            )
        ]

        print(
            "TRIMMED:",
            trimmed
        )

        if not trimmed:

            trimmed = prices

        estimated = round(
            statistics.median(
                trimmed
            )
        )

        print(
            "ESTIMATED:",
            estimated
        )

        print("=========================")

        confidence = "medium"

        if len(trimmed) >= 10:
            confidence = "high"

        return {

            "estimated": estimated,

            "low": min(trimmed),

            "high": max(trimmed),

            "confidence": confidence
        }

    except Exception as e:

        print(
            "PRICING ERROR:",
            str(e)
        )

        return {
            "estimated": None,
            "low": None,
            "high": None,
            "confidence": "low"
        }