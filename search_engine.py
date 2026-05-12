import re
import json
import httpx

from bs4 import BeautifulSoup
from difflib import SequenceMatcher

from utils import safe_int


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def normalize_title(title):

    title = title.lower()

    title = re.sub(
        r"[^a-zæøå0-9 ]",
        "",
        title
    )

    title = re.sub(r"\s+", " ", title)

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
            f"https://www.dba.dk/soeg/?soeg={query}"
        )

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True,
            )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        results = []

        cards = soup.select("article")

        for card in cards[:20]:

            text = card.get_text(
                " ",
                strip=True
            )

            price_match = re.search(
                r"(\\d[\\d\\.]*)\\s*kr",
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

            image = None

            img = card.select_one("img")

            if img:
                image = (
                    img.get("src")
                    or img.get("data-src")
                )

            results.append({
                "source": "DBA",
                "title": text[:200],
                "price": price,
                "image": image,
                "url": url,
            })

        return results


class LauritzScraper:

    async def search(self, query):

        url = (
            f"https://www.lauritz.com/da/auctions/search/{query}"
        )

        async with httpx.AsyncClient(timeout=30) as client:

            response = await client.get(
                url,
                headers=HEADERS,
                follow_redirects=True,
            )

        html = response.text

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        if not match:
            return []

        data = json.loads(match.group(1))

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

        results = []

        for item in found:

            title = item.get("title")

            if not title:
                continue

            prices = item.get("prices", {})

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

            price = current_bid or estimate

            if not price:
                continue

            image = item.get(
                "defaultImageUrl"
            )

            if image and not image.startswith("http"):
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

        return results