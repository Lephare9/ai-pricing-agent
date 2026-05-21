import re
import statistics


NEGATIVE_WORDS = [

    "samling",
    "collector",
    "limited",
    "museum",
    "investering",
    "køb trygt med dba",
    "betalingsoversigt",
    "alttext.dba",
]


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


def tokenize(text):

    if not text:
        return []

    words = re.findall(
        r'\w+',
        text.lower()
    )

    return [

        w for w in words

        if len(w) > 2
    ]


def score_result(query, title):

    if not title:
        return 0

    title_lower = title.lower()

    for negative in NEGATIVE_WORDS:

        if negative in title_lower:
            return -10

    query_words = tokenize(query)

    title_words = tokenize(title)

    score = 0

    overlap = len(
        set(query_words)
        &
        set(title_words)
    )

    score += overlap * 4

    # exact phrase bonus

    if query.lower() in title_lower:
        score += 6

    return score


def remove_outliers(prices):

    if len(prices) < 4:
        return prices

    q1 = statistics.quantiles(
        prices,
        n=4
    )[0]

    q3 = statistics.quantiles(
        prices,
        n=4
    )[2]

    iqr = q3 - q1

    lower = q1 - (
        1.5 * iqr
    )

    upper = q3 + (
        1.0 * iqr
    )

    filtered = [

        p for p in prices

        if lower <= p <= upper
    ]

    if filtered:
        return filtered

    return prices


def calculate_price(results, query=""):

    try:

        scored_results = []

        for item in results:

            title = item.get(
                "title",
                ""
            )

            score = score_result(
                query,
                title
            )

            scored_results.append({

                "item": item,
                "score": score
            })

        scored_results = sorted(
            scored_results,
            key=lambda x: x["score"],
            reverse=True
        )

        top_results = [

            r for r in scored_results

            if r["score"] >= 2
        ]

        if not top_results:
            top_results = scored_results[:5]

        top_results = top_results[:8]

        print("")
        print("===================")
        print("RELEVANCE DEBUG")

        for r in top_results:

            print(
                r["score"],
                "-",
                r["item"].get(
                    "title",
                    ""
                )[:160]
            )

        print("===================")

        prices = []

        for scored in top_results:

            item = scored["item"]

            price = extract_price(
                item.get("price")
            )

            if price:
                prices.append(price)

        prices = sorted(prices)

        print("")
        print("===================")
        print("RAW PRICES:")
        print(prices)

        if not prices:

            print("NO PRICES FOUND")
            print("===================")

            return {

                "estimated": None,
                "low": None,
                "high": None,
                "confidence": "low"
            }

        filtered = remove_outliers(
            prices
        )

        print("")
        print("FILTERED PRICES:")
        print(filtered)

        estimated = round(
            statistics.median(
                filtered
            )
        )

        print("")
        print("ESTIMATED:")
        print(estimated)

        print("===================")

        confidence = "low"

        if len(filtered) >= 5:
            confidence = "medium"

        if len(filtered) >= 8:
            confidence = "high"

        return {

            "estimated": estimated,

            "low": min(filtered),

            "high": max(filtered),

            "confidence": confidence
        }

    except Exception as e:

        print("")
        print("===================")
        print("PRICING ERROR:")
        print(str(e))
        print("===================")

        return {

            "estimated": None,
            "low": None,
            "high": None,
            "confidence": "low"
        }