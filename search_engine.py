import re
import json
import httpx

from bs4 import BeautifulSoup
from difflib import SequenceMatcher

from utils import safe_int


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def normalize_title(title):

    title = title.lower()

    title = re.sub(
        r"[^a-zæøå0-9 ]",
        "",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def deduplicate_results(results):

    unique = []

    for item in results:

        title = normalize_title(
            item.get("title", "")
        )

        price = item.get("price")

        duplicate = False

        for existing in unique:

            existing_title = normalize_title(
                existing.get("title", "")
            )

            sim = SequenceMatcher(
                None,
                title,
                existing_title
            ).ratio()

            if (
                sim > 0.88
                and existing.get("price") == price
            ):
                duplicate = True
                break

        if not duplicate:
            unique.append(item)

    return unique


class DBAScraper:

    async def search(self, query):

        url = (
            "https://www.dba.dk/soeg/"
            f"?soeg={query}"
        )

        print("\n===================")
        print("DBA QUERY:", query)
        print("DBA URL:", url)

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                url,
                headers=HEADERS,
            )

        print("DBA STATUS:", response.status_code)
        print("DBA HTML:", response.text[:1000])

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        cards = soup.find_all(
            [
                "article",
                "div"
            ]
        )

        print("DBA CARDS FOUND:", len(cards))

        for card in cards:

            text = card.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            price_match = re.search(
                r"(\d[\d\.]*)\s*kr",
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

            title = text[:250]

            image = None

            img = card.find("img")

            if img:

                image = (
                    img.get("src")
                    or img.get("data-src")
                )

            results.append({
                "source": "DBA",
                "title": title,
                "price": price,
                "image": image,
                "url": url,
            })

        print("DBA RESULTS:", len(results))

        return results[:40]


class LauritzScraper:

    async def search(self, query):

        url = (
            "https://www.lauritz.com/da/"
            f"auctions/search/{query}"
        )

        print("\n===================")
        print("LAURITZ QUERY:", query)

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                url,
                headers=HEADERS,
            )

        print(
            "LAURITZ STATUS:",
            response.status_code
        )

        html = response.text

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        if not match:

            print(
                "LAURITZ: NO JSON FOUND"
            )

            return []

        data = json.loads(
            match.group(1)
        )

        found = []

        def walk(obj):

            if isinstance(obj, dict):

                if (
                    "title" in obj
                    and (
                        "lotId" in obj
                        or "auctionId" in obj
                    )
                ):
                    found.append(obj)

                for value in obj.values():
                    walk(value)

            elif isinstance(obj, list):

                for item in obj:
                    walk(item)

        walk(data)

        print(
            "LAURITZ ITEMS FOUND:",
            len(found)
        )

        results = []

        for item in found:

            title = item.get("title")

            if not title:
                continue

            prices = item.get(
                "prices",
                {}
            )

            estimate = (
                prices.get("estimated", {})
                .get("showroom", {})
                .get("amount")
            )

            current_bid = (
                prices.get("currentBid", {})
                .get("showroom", {})
                .get("amount")
            )

            price = (
                current_bid
                or estimate
            )

            if not price:
                continue

            image = item.get(
                "defaultImageUrl"
            )

            if (
                image
                and not image.startswith("http")
            ):
                image = (
                    "https://images.lauritz.com/"
                    + image
                )

            results.append({
                "source": "Lauritz",
                "title": title,
                "price": price,
                "image": image,
                "url": url,
            })

        print(
            "LAURITZ RESULTS:",
            len(results)
        )

        return results[:40]