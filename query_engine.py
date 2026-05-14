def build_queries(gemini_data):

    queries = []

    primary = gemini_data.get(
        "primary_query"
    )

    if primary:

        q = (
            primary
            .strip()
            .lower()
        )

        queries.append(q)

    if not queries:

        title = gemini_data.get(
            "title",
            ""
        )

        if title:

            queries.append(
                title
                .strip()
                .lower()
            )

    return queries[:1]