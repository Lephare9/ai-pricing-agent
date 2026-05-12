import re


def safe_int(value):

    if value is None:
        return None

    text = str(value)

    text = (
        text
        .replace(".", "")
        .replace(",", "")
        .replace("kr.", "")
        .replace("kr", "")
        .replace("DKK", "")
        .strip()
    )

    match = re.search(r"(\d+)", text)

    if not match:
        return None

    try:
        return int(match.group(1))
    except:
        return None