import re
import httpx

from bs4 import BeautifulSoup

from utils import safe_int


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0"
    )
}


async def search_dba(query):

    print("")
    print("===================")
    print(f"DBA QUERY: {query}")

    url = (
        "https://www.dba.dk/soeg/"
        f"?soeg={query}"
    )

    results = []

    try:

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers=HEADERS,
        ) as client:

            response = await client.get(url)

        print(
            f"DBA STATUS: {response.status_code}"
        )

        html = response.text

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        cards = soup.select(
            '[class*="listing"], article'
        )

        print(
            f"DBA RESULTS: {len(cards)}"
        )

        for card in cards[:30]:

            text = card.get_text(
                " ",
                strip=True
            )

            if len(text) < 20:
                continue

            price_match = re.search(
                r'(\d[\d\. ]*)\s*kr',
                text,
                re.I
            )

            if not price_match:
                continue

            price = safe_int(
                price_match.group(1)
            )

            if not price:
                continue

            if price < 25:
                continue

            if price > 100000:
                continue

            lines = text.split()

            title = " ".join(
                lines[:18]
            )

            title = title.strip()

            results.append({
                "title": title,
                "price": price,
            })

        # dedupe
        unique = []

        seen = set()

        for item in results:

            key = (
                item["title"][:40],
                item["price"]
            )

            if key in seen:
                continue

            seen.add(key)

            unique.append(item)

        print(
            f"DBA CLEAN RESULTS: {len(unique)}"
        )

        return unique[:10]

    except Exception as e:

        print(
            f"DBA ERROR: {e}"
        )

        return []