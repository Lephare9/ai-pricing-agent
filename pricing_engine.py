import re
import statistics


NEGATIVE_WORDS = [

    "sjælden",
    "unik",
    "collector",
    "samler",
    "limited",
    "museum",
    "investering",
    "ældgammel"
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


def normalize_word(word):

    word = word.lower().strip()

    replacements = {

        "jakker": "jakke",
        "dunjakke": "jakke",
        "pufferjakke": "jakke",
        "vinterjakke": "jakke",

        "lamper": "lampe",
        "pendellampe": "lampe",
        "bordlampe": "lampe",
        "gulvlampe": "lampe",

        "stole": "stol",
        "barstol": "stol",
        "lænestole": "lænestol"
    }

    return replacements.get(
        word,
        word
    )


def tokenize(text):

    if not text:
        return []

    words = re.findall(
        r'\w+',
        text.lower()
    )

    normalized = [

        normalize_word(w)

        for w in words

        if len(w) > 2
    ]

    return normalized


def score_result(query, title):

    if not title:
        return 0

    query_words = tokenize(query)

    title_words = tokenize(title)

    score = 0

    # exact token matches

    for word in query_words:

        if word in title_words:
            score += 3

    # bonus for multiple matches

    overlap = len(

        set(query_words)
        &
        set(title_words)
    )

    score += overlap

    # penalize suspicious words

    title_lower = title.lower()

    for negative in NEGATIVE_WORDS:

        if negative in title_lower:
            score -= 3

    return score


def calculate_price(results, query=""):

    try:

        scored_results = []

        for item in results:

            title = ""

            if isinstance(item, dict):

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

        # keep only relevant hits

        top_results = [

            r for r in scored_results

            if r["score"] >= 2
        ]

        # fallback

        if not top_results:

            top_results = scored_results[:5]

        # limit amount

        top_results = top_results[:6]

        print("===== RELEVANCE DEBUG =====")

        for r in top_results:

            print(
                r["score"],
                "-",
                r["item"].get(
                    "title",
                    ""
                )
            )

        print("===========================")

        prices = []

        for scored in top_results:

            item = scored["item"]

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