# Retrieval. Chunks by default, so the agent path never pays for a second model call.
from __future__ import annotations

from plugmybrain import config

MODES = ("chunks", "graph")


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
        return await cognee.search(
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[dataset],
            top_k=top_k,
        )

    # CHUNKS makes no completion call, so this is already the cheap path. Deliberately without
    # only_context: that flag collapses the hits into one joined string and throws away the
    # per-chunk metadata, so nothing downstream can say which file an answer came from.
    return await cognee.search(
        query_text=query,
        query_type=SearchType.CHUNKS,
        datasets=[dataset],
        top_k=top_k,
    )


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
