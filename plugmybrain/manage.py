# `pmb list` and `pmb reset`: what the brain holds, and how to throw it away.
#
# Both are deliberately blunt about the one thing that matters — the markdown on disk is the
# real memory, and the database is a derived index that can always be rebuilt from it.
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugmybrain import config


@dataclass
class DatasetRow:
    name: str
    documents: int
    created: str


@dataclass
class Status:
    target: Path
    name: str
    markdown: int
    skipped: int
    human_notes: int
    generated_notes: int
    ingested: int
    datasets: list[DatasetRow] = field(default_factory=list)
    chunks: int = 0
    database: str = ""
    size: str = ""


@dataclass
class ResetReport:
    scope: str
    documents: int
    generated: Path | None
    kept: Path | None


async def _pool():
    import asyncpg

    return await asyncpg.connect(**config.db_connect_kwargs())


def _on_disk(target: Path) -> tuple[int, int, int, int]:
    """(markdown, skipped, human notes, generated notes) for a folder, counted from the files.

    This is the "berapa jadi berapa" half of `pmb list`: what the folder holds against what the
    database actually took, so a gap is visible instead of assumed away.
    """
    included, skipped = config.collect_documents(target)
    human = target / config.HUMAN
    generated = target / config.GENERATED
    # graph/ is excluded so a digest never eats its own output, but that is by design rather
    # than a refused secret. Counting it under "skipped" would report the tool's own notes as
    # something suspicious it declined to read.
    refused = [p for p in skipped if not p.is_relative_to(generated)]
    return (
        len(included),
        len(refused),
        len(list(human.rglob("*.md"))) if human.is_dir() else 0,
        len(list(generated.rglob("*.md"))) if generated.is_dir() else 0,
    )


async def status(target: Path) -> Status:
    """Everything known about the memory: the database, and the folder it came from."""
    config.configure(models=False)

    target = target.resolve()
    name = config.namespace(target)
    markdown, skipped, human, generated = _on_disk(target)

    connection = await _pool()
    try:
        rows = await connection.fetch(
            "SELECT ds.name, count(dd.data_id) AS documents, min(ds.created_at) AS created "
            "FROM datasets ds LEFT JOIN dataset_data dd ON dd.dataset_id = ds.id "
            "GROUP BY ds.name ORDER BY ds.name"
        )
        database = str(config.db_connect_kwargs()["database"])
        size = await connection.fetchval("SELECT pg_size_pretty(pg_database_size($1))", database)

        # Cognee makes one table per collection, so the chunk total is the sum across every
        # table carrying a vector column rather than a single count.
        chunks = 0
        for table in await connection.fetch(
            "SELECT DISTINCT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND udt_name = 'vector'"
        ):
            chunks += await connection.fetchval(f'SELECT count(*) FROM "{table["table_name"]}"')
    finally:
        await connection.close()

    datasets = [
        DatasetRow(r["name"], r["documents"], str(r["created"])[:19] if r["created"] else "")
        for r in rows
    ]
    return Status(
        target=target,
        name=name,
        markdown=markdown,
        skipped=skipped,
        human_notes=human,
        generated_notes=generated,
        ingested=next((d.documents for d in datasets if d.name == name), 0),
        datasets=datasets,
        chunks=chunks,
        database=database,
        size=size or "",
    )


async def reset(target: Path, everything: bool = False) -> ResetReport:
    """Throw away the derived memory. Never the markdown.

    `memory/` is what a person wrote and `pmb digest` can rebuild everything else from it, so
    this deletes the database rows and the generated `graph/` folder and stops there.
    """
    config.configure()
    import cognee

    target = target.resolve()
    generated = target / config.GENERATED
    name = config.namespace(target)

    if everything:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(graph=True, vector=True, metadata=True)
        documents = -1
    else:
        connection = await _pool()
        try:
            rows = await connection.fetch(
                "SELECT dd.data_id, dd.dataset_id FROM dataset_data dd "
                "JOIN datasets ds ON ds.id = dd.dataset_id WHERE ds.name = $1",
                name,
            )
        finally:
            await connection.close()
        if not rows:
            raise SystemExit(
                f"nothing named {name!r} in the database. `pmb list` shows what is there."
            )
        # cognee's own delete, not a DELETE statement: the rows in Postgres are three stores at
        # once, and removing the relational row by hand orphans the vectors and the graph nodes.
        for row in rows:
            await cognee.delete(data_id=row["data_id"], dataset_id=row["dataset_id"], mode="hard")
        documents = len(rows)

    if generated.is_dir():
        shutil.rmtree(generated)

    return ResetReport(
        scope="everything" if everything else name,
        documents=documents,
        generated=generated,
        kept=(target / config.HUMAN) if (target / config.HUMAN).is_dir() else None,
    )
