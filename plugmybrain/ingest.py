# Ingestion: add, cognify, index. This file is `pmb ingest`, `pmb sync`, and the one-shot
# `cognee-ingest` container. Never co-resident with serving on a 2 GiB VM.
from __future__ import annotations

import inspect
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from plugmybrain import config

# Table and column names come from information_schema, never from a user, but Postgres will not
# bind an identifier so they still reach the DDL by interpolation. The allowlist is what makes
# that safe, and anything it rejects is reported rather than skipped in silence.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64
HNSW_EF_SEARCH = 64

# pgvector's own sizing guidance: lists = rows / 1000 up to a million rows.
IVFFLAT_ROWS_PER_LIST = 1000

# `WITH (lists='100')` inside pg_indexes.indexdef, so a stale index can be spotted.
_LISTS = re.compile(r"lists\s*=\s*'?(\d+)'?")


@dataclass
class IngestReport:
    dataset: str
    ingested: int = 0
    skipped: list[Path] = field(default_factory=list)
    indexes_created: list[str] = field(default_factory=list)
    indexes_skipped: list[str] = field(default_factory=list)
    indexes_rebuild_due: list[str] = field(default_factory=list)
    indexes_refused: list[str] = field(default_factory=list)
    estimate: object | None = None


def choose_index(rows: int, kind: str = config.INDEX_KIND) -> str:
    """Which index a table of `rows` vectors should get: exact, ivfflat or hnsw.

    `exact` means no index at all. Below the threshold that is the right answer, not a
    concession: pgvector sizes IVFFlat at lists = rows / 1000, so a few hundred chunks would
    produce a single-list index, which is a sequential scan carrying index overhead. Exact
    search over the same rows is faster and has perfect recall.
    """
    if kind != "auto":
        return kind
    return "exact" if rows < config.FLAT_THRESHOLD else "ivfflat"


async def ensure_vector_index() -> IngestReport:
    """Give every pgvector column the index its row count deserves, and say which and why.

    Cognee's pgvector adapter creates the table and the vector column but no index at all, and
    it creates a new table per collection. So this runs after every ingest rather than once:
    a one-time CREATE INDEX goes stale the moment a new dataset appears.

    Runs after the data is loaded, which IVFFlat requires. It has a training step, so an
    IVFFlat index built on an empty table has near-useless recall and fails silently.
    """
    import asyncpg

    report = IngestReport(dataset="")
    connection = await asyncpg.connect(**config.db_connect_kwargs())
    try:
        columns = await connection.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND udt_name = 'vector'"
        )
        existing = {
            row["tablename"]: row["indexdef"]
            for row in await connection.fetch(
                "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND (indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%')"
            )
        }
        built: set[str] = set()

        for row in columns:
            table, column = row["table_name"], row["column_name"]
            if not (_IDENTIFIER.match(table) and _IDENTIFIER.match(column)):
                report.indexes_refused.append(f"{table}.{column}")
                continue

            count = await connection.fetchval(f'SELECT count(*) FROM "{table}"')

            if table in existing:
                match = _LISTS.search(existing[table])
                # An IVFFlat sized for a tenth of the current rows still answers, just badly.
                # Reported rather than rebuilt: dropping an index on a live database unasked
                # is not a thing to do.
                if match and count > int(match.group(1)) * IVFFLAT_ROWS_PER_LIST * 10:
                    report.indexes_rebuild_due.append(
                        f"{table} has {count} rows against lists={match.group(1)}"
                    )
                continue

            kind = choose_index(count)
            if kind == "exact":
                report.indexes_skipped.append(f"{table} ({count} rows, exact search is faster)")
                continue

            # vector_cosine_ops, not the vector_l2_ops default: cognee searches by cosine
            # distance, and an index built for the wrong operator is never used.
            if kind == "ivfflat":
                lists = max(1, count // IVFFLAT_ROWS_PER_LIST)
                index = f"{table}_{column}_ivfflat"
                await connection.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" '
                    f'USING ivfflat ("{column}" vector_cosine_ops) WITH (lists = {lists})'
                )
                report.indexes_created.append(f"{index} (lists={lists}, {count} rows)")
            else:
                index = f"{table}_{column}_hnsw"
                await connection.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" '
                    f'USING hnsw ("{column}" vector_cosine_ops) '
                    f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
                )
                report.indexes_created.append(f"{index} ({count} rows)")
            built.add(kind)

        # Cognee opens its own connections, so neither probes nor ef_search can be set per
        # session. Both default to a value tuned for speed over recall.
        database = str(config.db_connect_kwargs()["database"])
        if not _IDENTIFIER.match(database):
            report.indexes_refused.append(f"database {database}: search depth not set")
        elif "ivfflat" in built:
            lists = max(
                1,
                max(int(m.group(1)) for e in report.indexes_created if (m := _LISTS.search(e))),
            )
            probes = max(1, round(math.sqrt(lists)))
            await connection.execute(f'ALTER DATABASE "{database}" SET ivfflat.probes = {probes}')
        elif "hnsw" in built:
            await connection.execute(
                f'ALTER DATABASE "{database}" SET hnsw.ef_search = {HNSW_EF_SEARCH}'
            )
    finally:
        await connection.close()
    return report


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

    Idempotent: cognee loads incrementally, and ensure_vector_index only creates what is
    missing.
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

    indexes = await ensure_vector_index()
    report.indexes_created = indexes.indexes_created
    report.indexes_skipped = indexes.indexes_skipped
    report.indexes_rebuild_due = indexes.indexes_rebuild_due
    report.indexes_refused = indexes.indexes_refused
    return report
