# Retrieval. Chunks and their sources only: the agent asking already has a model.
from __future__ import annotations

from plugmybrain import config

# cognee's `datasets` argument does not scope a search, so fetch more and filter here
OVERFETCH = 6
MAX_OVERFETCH = 200


async def _fetch(sql: str, *args) -> list:
    """Query Postgres, treating "no tables yet" as "nothing digested yet"."""
    import asyncpg

    connection = await asyncpg.connect(**config.db_connect_kwargs())
    try:
        return await connection.fetch(sql, *args)
    except asyncpg.exceptions.UndefinedTableError:
        return []
    finally:
        await connection.close()


async def brains() -> list[tuple[str, int]]:
    """Every memory in the database and how many documents it holds."""
    rows = await _fetch(
        "SELECT ds.name, count(dd.data_id) AS documents FROM datasets ds "
        "LEFT JOIN dataset_data dd ON dd.dataset_id = ds.id "
        "GROUP BY ds.name ORDER BY ds.name"
    )
    return [(row["name"], row["documents"]) for row in rows]


async def members(names: list[str]) -> tuple[set[str], set[str]]:
    """(document ids, document names) in these memories, from Postgres, the authority."""
    rows = await _fetch(
        "SELECT d.id, d.name FROM data d "
        "JOIN dataset_data dd ON dd.data_id = d.id "
        "JOIN datasets ds ON ds.id = dd.dataset_id "
        "WHERE ds.name = ANY($1)",
        names,
    )
    return {str(row["id"]) for row in rows}, {row["name"] for row in rows}


def names(brain: str | list[str]) -> list[str]:
    """One memory or several; a tool argument passes a set comma-separated."""
    values = brain if isinstance(brain, list) else brain.split(",")
    chosen = [value.strip().lower() for value in values if value.strip()]
    if not chosen:
        raise ValueError("no brain given")
    return chosen


def belongs(item: object, ids: set[str], titles: set[str]) -> bool:
    """True when a chunk comes from one of the chosen memories.

    By document id, because two brains often share a file name such as README.md.
    """
    if not isinstance(item, dict):
        return False
    document_id = item.get("document_id")
    if document_id:
        return str(document_id) in ids
    return item.get("document_name") in titles


def sources(results: list) -> list[str]:
    """The files a result set came from, in order, de-duplicated, with `.md` restored."""
    seen: list[str] = []
    for item in results:
        name = item.get("document_name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            continue
        # Not Path.suffix: `commit.rules` already has one
        if not name.lower().endswith(tuple(config.DOCUMENT_SUFFIXES)):
            name = f"{name}.md"
        if name not in seen:
            seen.append(name)
    return seen


async def search(query: str, brain: str | list[str], top_k: int = 15) -> list[dict]:
    """Search one memory, or several, and return only chunks that really belong to them."""
    from plugmybrain import manage

    chosen = names(brain)
    problem = await manage.embedding_mismatch()
    if problem:
        raise ValueError(problem)

    ids, titles = await members(chosen)
    if not ids:
        raise ValueError(
            f"no documents in {', '.join(chosen)}. Digest it first, or check the name: "
            "it is the folder's own name, lowercased."
        )

    import cognee
    from cognee import SearchType

    # Not only_context: that joins the hits into one string and drops which file each came from
    results = await cognee.search(
        query_text=query,
        query_type=SearchType.CHUNKS,
        datasets=chosen,
        top_k=min(MAX_OVERFETCH, top_k * OVERFETCH * len(chosen)),
    )
    return [r for r in results if belongs(r, ids, titles)][:top_k]
