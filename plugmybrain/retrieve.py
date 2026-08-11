# Retrieval. Chunks by default, so the agent path never pays for a second model call.
from __future__ import annotations

from plugmybrain import config

MODES = ("chunks", "graph")

# Cognee keeps every dataset in one vector collection and its `datasets` argument does not
# scope the search, so a query for one project returns another's documents. Postgres does know
# which document belongs to where, so membership is enforced here instead. Over-fetching gives
# the filter something to cut: ask for more than requested, keep only this dataset's, then trim.
OVERFETCH = 6
MAX_OVERFETCH = 200


async def dataset_documents(dataset: str) -> set[str]:
    """The document names in one dataset, from Postgres, which is the authority on membership."""
    import asyncpg

    connection = await asyncpg.connect(**config.db_connect_kwargs())
    try:
        rows = await connection.fetch(
            "SELECT d.name FROM data d "
            "JOIN dataset_data dd ON dd.data_id = d.id "
            "JOIN datasets ds ON ds.id = dd.dataset_id "
            "WHERE ds.name = $1",
            dataset,
        )
    finally:
        await connection.close()
    return {row["name"] for row in rows}


async def search(query: str, dataset: str, mode: str = "chunks", top_k: int = 15) -> list:
    """Search one dataset. `chunks` returns sourced context with no completion step;
    `graph` spends an extra model call to synthesise an answer from the graph.

    The dataset is required rather than defaulted, which is what keeps projects isolated.
    """
    if mode not in MODES:
        raise SystemExit(f"unknown mode {mode!r}. Use one of: {', '.join(MODES)}")

    config.configure()
    import cognee
    from cognee import SearchType

    if mode == "graph":
        # No filtering is possible here: GRAPH_COMPLETION returns prose, not chunks, so there
        # is no per-document metadata to check membership against. This mode can still mix
        # projects, which is one more reason chunks is the default.
        return await cognee.search(
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[dataset],
            top_k=top_k,
        )

    members = await dataset_documents(dataset)
    if not members:
        raise SystemExit(
            f"dataset {dataset!r} holds no documents. Ingest it first, or check the name: "
            "it is the folder's own name, lowercased."
        )

    # CHUNKS makes no completion call, so this is already the cheap path. Deliberately without
    # only_context: that flag collapses the hits into one joined string and throws away the
    # per-chunk metadata, so nothing downstream can say which file an answer came from, and
    # the filter below would have nothing to work with.
    results = await cognee.search(
        query_text=query,
        query_type=SearchType.CHUNKS,
        datasets=[dataset],
        top_k=min(MAX_OVERFETCH, top_k * OVERFETCH),
    )
    kept = [r for r in results if isinstance(r, dict) and r.get("document_name") in members]
    return kept[:top_k]


def sources(results: list) -> list[str]:
    """The files a result set came from, in order, de-duplicated.

    Cognee returns `document_name` without an extension, so `commit.rules` becomes
    `commit.rules.md`. The vault is markdown; anything already carrying a suffix is left alone.
    """
    seen: list[str] = []
    for item in results:
        name = item.get("document_name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            continue
        # Not Path().suffix: `commit.rules` already has one (`.rules`), so a suffix test
        # silently leaves the vault's own naming convention without its extension.
        if not name.lower().endswith(tuple(config.DOCUMENT_SUFFIXES)):
            name = f"{name}.md"
        if name not in seen:
            seen.append(name)
    return seen
