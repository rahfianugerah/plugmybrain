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
    generated: list[Path]
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
    name = config.namespace(target)
    # Counted in the vault, not here: a digested folder is only ever read, so nothing this tool
    # generated is inside it. Nothing below is a write path, and that is the point.
    written = sum(
        len(list(directory.rglob("*.md")))
        for sub in config.GENERATED_SUBDIRS
        if (directory := config.DOCS / config.GENERATED / sub / name).is_dir()
    )
    return (
        len(included),
        len(skipped),
        len(list(human.rglob("*.md"))) if human.is_dir() else 0,
        written,
    )


async def status(target: Path, scan: bool = True) -> Status:
    """Everything known about the memory: the database, and the folder it came from.

    `scan=False` skips the disk walk, which is what a root wants: counting its markdown means
    counting every child's, and the sum of things that were digested separately is not a number
    that means anything.
    """
    config.configure()

    target = target.resolve()
    name = config.namespace(target)
    markdown, skipped, human, generated = _on_disk(target) if scan else (0, 0, 0, 0)

    import asyncpg

    connection = await _pool()
    try:
        try:
            rows = await connection.fetch(
                "SELECT ds.name, count(dd.data_id) AS documents, min(ds.created_at) AS created "
                "FROM datasets ds LEFT JOIN dataset_data dd ON dd.dataset_id = ds.id "
                "GROUP BY ds.name ORDER BY ds.name"
            )
        except asyncpg.exceptions.UndefinedTableError:
            # Cognee creates its schema on the first `add`, so before any digest these tables
            # do not exist. That is an empty brain, not a broken one.
            rows = []
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
    this deletes the database rows and this brain's generated notes in the vault, and stops.
    """
    config.configure()
    import cognee

    target = target.resolve()
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

    # This brain's folder under each kind, never the kind folder itself: another brain's notes
    # live beside it, and `graph/README.md` above it is hand-written and committed.
    removed = []
    for sub in config.GENERATED_SUBDIRS:
        directory = config.DOCS / config.GENERATED / sub / name
        if directory.is_dir():
            shutil.rmtree(directory)
            removed.append(directory)

    return ResetReport(
        scope="everything" if everything else name,
        documents=documents,
        generated=removed,
        kept=(target / config.HUMAN) if (target / config.HUMAN).is_dir() else None,
    )
