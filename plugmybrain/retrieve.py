# Retrieval. Chunks only: this is a RAG for a coding agent, which already has a model and does
# not need a second one writing prose over the results.
from __future__ import annotations

from plugmybrain import config

# Cognee keeps every memory in one vector collection and its `datasets` argument does not scope
# the search, so a query for one project returns another's documents. Postgres does know which
# document belongs where, so membership is enforced here. Over-fetching gives the filter
# something to cut: ask for more than requested, keep only this memory's, then trim.
OVERFETCH = 6
MAX_OVERFETCH = 200


async def _fetch(sql: str, *args) -> list:
    """Query Postgres, treating "no tables yet" as "nothing digested yet".

    Cognee creates its schema on the first `add`, so before any digest these tables genuinely do
    not exist. Left to asyncpg the agent's first call answers `relation "datasets" does not
    exist`, which reads as a broken install rather than an empty one.
    """
    import asyncpg

    connection = await asyncpg.connect(**config.db_connect_kwargs())
    try:
        return await connection.fetch(sql, *args)
    except asyncpg.exceptions.UndefinedTableError:
        return []
    finally:
        await connection.close()


async def brains() -> list[tuple[str, int]]:
    """Every memory in the database and how many documents it holds, for `/pmb-map`."""
    rows = await _fetch(
        "SELECT ds.name, count(dd.data_id) AS documents FROM datasets ds "
        "LEFT JOIN dataset_data dd ON dd.dataset_id = ds.id "
        "GROUP BY ds.name ORDER BY ds.name"
    )
    return [(row["name"], row["documents"]) for row in rows]


async def documents(names: list[str]) -> set[str]:
    """The document names in these memories, from Postgres, which is the authority."""
    rows = await _fetch(
        "SELECT d.name FROM data d "
        "JOIN dataset_data dd ON dd.data_id = d.id "
        "JOIN datasets ds ON ds.id = dd.dataset_id "
        "WHERE ds.name = ANY($1)",
        names,
    )
    return {row["name"] for row in rows}


def names(brain: str | list[str]) -> list[str]:
    """One memory or several. A comma-separated string is how a tool argument passes a set."""
    values = brain if isinstance(brain, list) else brain.split(",")
    chosen = [value.strip().lower() for value in values if value.strip()]
    if not chosen:
        raise ValueError("no brain given")
    return chosen


def sources(results: list) -> list[str]:
    """The files a result set came from, in order, de-duplicated.

    Cognee returns `document_name` without an extension, so `commit.rules` becomes
    `commit.rules.md`. Not `Path().suffix`: `commit.rules` already has one (`.rules`), so a
    suffix test silently leaves the vault's own naming convention without its extension.
    """
    seen: list[str] = []
    for item in results:
        name = item.get("document_name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            continue
        if not name.lower().endswith(tuple(config.DOCUMENT_SUFFIXES)):
            name = f"{name}.md"
        if name not in seen:
            seen.append(name)
    return seen


async def search(query: str, brain: str | list[str], top_k: int = 15) -> list[dict]:
    """Search one memory, or several, and return only chunks that really belong to them."""
    chosen = names(brain)

    import cognee
    from cognee import SearchType

    members = await documents(chosen)
    if not members:
        raise ValueError(
            f"no documents in {', '.join(chosen)}. Digest it first, or check the name: "
            "it is the folder's own name, lowercased."
        )

    # Deliberately without only_context: that flag collapses the hits into one joined string and
    # throws away the per-chunk metadata, so nothing downstream can say which file an answer
    # came from, and the filter below would have nothing to work with.
    results = await cognee.search(
        query_text=query,
        query_type=SearchType.CHUNKS,
        datasets=chosen,
        top_k=min(MAX_OVERFETCH, top_k * OVERFETCH * len(chosen)),
    )
    kept = [r for r in results if isinstance(r, dict) and r.get("document_name") in members]
    return kept[:top_k]
