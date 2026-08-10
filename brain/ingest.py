# Ingestion: add, cognify, index. This file is `brain ingest`, `brain sync` and the Cloud Run Job.
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path

from brain import config

# Table and column names come from information_schema, never from a user, but Postgres will not
# bind an identifier so they still reach the DDL by interpolation. The allowlist is what makes
# that safe, and anything it rejects is reported rather than skipped in silence.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64
HNSW_EF_SEARCH = 64


@dataclass
class IngestReport:
    dataset: str
    ingested: int = 0
    skipped: list[Path] = field(default_factory=list)
    indexes_created: list[str] = field(default_factory=list)
    indexes_refused: list[str] = field(default_factory=list)
    estimate: object | None = None


async def ensure_hnsw() -> tuple[list[str], list[str]]:
    """Create a missing HNSW index on every pgvector column. Returns (created, refused).

    Cognee's pgvector adapter creates the table and the vector column but no index at all, and
    it creates a new table per collection. So this runs after every ingest rather than once:
    a one-time CREATE INDEX goes stale the moment a new dataset appears.
    """
    import asyncpg

    created: list[str] = []
    refused: list[str] = []
    connection = await asyncpg.connect(**config.db_connect_kwargs())
    try:
        columns = await connection.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND udt_name = 'vector'"
        )
        already = {
            row["tablename"]
            for row in await connection.fetch(
                "SELECT tablename FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexdef ILIKE '%USING hnsw%'"
            )
        }
        for row in columns:
            table, column = row["table_name"], row["column_name"]
            if table in already:
                continue
            if not (_IDENTIFIER.match(table) and _IDENTIFIER.match(column)):
                refused.append(f"{table}.{column}")
                continue
            index = f"{table}_{column}_hnsw"
            # vector_cosine_ops, not the vector_l2_ops default: cognee searches by cosine
            # distance, and an index built for the wrong operator is never used.
            await connection.execute(
                f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" '
                f'USING hnsw ("{column}" vector_cosine_ops) '
                f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
            )
            created.append(index)

        # Cognee opens its own connections, so ef_search cannot be set per session.
        database = str(config.db_connect_kwargs()["database"])
        if _IDENTIFIER.match(database):
            await connection.execute(
                f'ALTER DATABASE "{database}" SET hnsw.ef_search = {HNSW_EF_SEARCH}'
            )
        else:
            refused.append(f"database {database}: ef_search not set")
    finally:
        await connection.close()
    return created, refused


async def _memify(cognee, dataset: str) -> None:
    """cognee 1.4.2 exports memify, but its definition could not be located to pin the
    signature, so the accepted arguments are read off the installed function."""
    parameters = inspect.signature(cognee.memify).parameters
    await cognee.memify(**({"datasets": [dataset]} if "datasets" in parameters else {}))


async def ingest(
    paths: list[Path],
    dataset: str,
    dry_run: bool = False,
    memify: bool = False,
) -> IngestReport:
    """Ingest every document under `paths` into `dataset`, then index it.

    Idempotent: cognee loads incrementally, and ensure_hnsw only creates what is missing.
    """
    config.configure()
    import cognee

    documents: list[Path] = []
    skipped: list[Path] = []
    for root in paths:
        if not root.is_dir():
            raise SystemExit(f"not a directory: {root}")
        found, blocked = config.collect_documents(root)
        documents.extend(found)
        skipped.extend(blocked)

    if not documents:
        raise SystemExit(f"no documents found under: {', '.join(str(p) for p in paths)}")

    report = IngestReport(dataset=dataset, ingested=len(documents), skipped=skipped)

    # add chunks and stores; cognify is the pass that calls the model. Estimating after the
    # add and before the cognify is what makes --dry-run tell you the real cost.
    await cognee.add([str(path) for path in documents], dataset_name=dataset)
    if dry_run:
        report.estimate = await cognee.cognify(datasets=[dataset], dry_run=True)
        return report

    await cognee.cognify(datasets=[dataset])
    if memify:
        await _memify(cognee, dataset)

    report.indexes_created, report.indexes_refused = await ensure_hnsw()
    return report
