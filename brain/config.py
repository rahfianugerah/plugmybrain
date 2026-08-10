# Paths, profile and cognee settings. One module, both profiles; BRAIN_PROFILE is the only switch.
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROFILE = os.getenv("BRAIN_PROFILE", "local")

# The vault is a sibling checkout by default, because that is how the two repos sit on disk.
VAULT = Path(os.getenv("BRAIN_VAULT", REPO_ROOT.parent / "docs")).resolve()

# Graphify output lands here, never inside the folder that was mapped.
GRAPH_DIR = Path(os.getenv("BRAIN_GRAPH_DIR", REPO_ROOT / "graph")).resolve()

# The only part of the vault this project may write to. Everything above it is human-authored.
VAULT_GENERATED = VAULT / "graph"

# The human control plane: rules and memory. Wins on conflict with any project dataset.
CURATED_DATASET = "curated"
CURATED_PATHS = (VAULT / "rules", VAULT / "memory")

# pgvector refuses to build an HNSW index on a `vector` column wider than this. Exceeding it
# does not fail loudly, it just leaves every search doing a sequential scan.
MAX_INDEXABLE_DIMENSIONS = 2000

# Documents only. Code structure is Graphify's job, and ingesting source would pay a model to
# rediscover what `brain map` already extracted for nothing.
DOCUMENT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".pdf", ".docx", ".csv"})

# Never read, whatever folder the tool is pointed at. Ingestion uploads file contents, so this
# is the last thing standing between an arbitrary target and a leaked key.
EXCLUDED_DIRS = frozenset(
    {
        "keys",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        "graph",
        "graphify-out",
        ".obsidian",
    }
)
EXCLUDED_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "credentials.json",
    "env-vars.yaml",
    "jwt-secret.txt",
)


def namespace(target: Path) -> str:
    """The dataset name for a mapped or ingested folder: its directory name, lowercased."""
    name = target.resolve().name.lower()
    if not name:
        raise ValueError(f"cannot derive a namespace from {target}")
    return name


def generated_path(*parts: str) -> Path:
    """A path inside the vault's generated area. Refuses to escape it, so a regeneration
    can never touch a human-authored note."""
    path = VAULT_GENERATED.joinpath(*parts).resolve()
    if not path.is_relative_to(VAULT_GENERATED.resolve()):
        raise ValueError(f"refusing to write outside {VAULT_GENERATED}: {path}")
    return path


def is_excluded(path: Path) -> bool:
    """True when a path must never be sent to the model.

    ponytail: name and directory matching only. A secret pasted into an ordinary .md still
    gets through; add a content scan here if that ever stops being an acceptable risk.
    """
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_NAMES)


def collect_documents(root: Path) -> tuple[list[Path], list[Path]]:
    """Split a folder into the documents that will be ingested and the files that will not.

    The skipped list is returned rather than discarded, because a silent skip reads as
    "covered everything" when it did not.
    """
    root = root.resolve()
    included: list[Path] = []
    skipped: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if is_excluded(path):
            skipped.append(path)
        elif path.suffix.lower() in DOCUMENT_SUFFIXES:
            included.append(path)
    return included, skipped


def db_connect_kwargs() -> dict[str, object]:
    """asyncpg connection arguments for the active profile."""
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ["DB_USERNAME"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
    }


def configure() -> None:
    """Load `.env`, derive the profile's settings, and fail fast on a bad one.

    Must run before `import cognee`, because cognee reads its configuration from the
    environment at import time.
    """
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    # Invariants of this design rather than user choices, so they are set, not read.
    os.environ.setdefault("DB_PROVIDER", "postgres")
    os.environ.setdefault("VECTOR_DB_PROVIDER", "pgvector")
    os.environ.setdefault("GRAPH_DATABASE_PROVIDER", "postgres")
    os.environ.setdefault("TELEMETRY_DISABLED", "1")

    missing = [
        key for key in ("DB_HOST", "DB_NAME", "DB_USERNAME", "DB_PASSWORD") if not os.getenv(key)
    ]
    if missing:
        raise SystemExit(
            f"missing in .env: {', '.join(missing)}. Copy .env.example and fill it in."
        )

    # Voyage is embeddings only, so the embedding key is separate from the chat key. Without
    # this check cognee silently falls back to LLM_API_KEY and Voyage rejects it with a 401
    # that names the wrong vendor.
    if not os.getenv("EMBEDDING_API_KEY"):
        raise SystemExit(
            "EMBEDDING_API_KEY is not set. Voyage needs its own key, separate from LLM_API_KEY."
        )

    # mcp-sampling borrows the MCP host's model and needs no key. Any other provider does.
    if os.getenv("LLM_PROVIDER") != "mcp-sampling" and not os.getenv("LLM_API_KEY"):
        raise SystemExit(
            "LLM_API_KEY is not set. Batch ingestion has no MCP host to sample from, "
            "so it needs a real chat key even when the interactive path does not."
        )

    dimensions = int(os.environ.setdefault("EMBEDDING_DIMENSIONS", "1024"))
    if dimensions > MAX_INDEXABLE_DIMENSIONS:
        raise SystemExit(
            f"EMBEDDING_DIMENSIONS={dimensions} exceeds {MAX_INDEXABLE_DIMENSIONS}, the widest "
            "vector pgvector will build an HNSW index on. Every search would fall back to a "
            "sequential scan. Use 1024."
        )

    # The vector store is the same Postgres as the relational store: one database, one backup.
    for key in ("HOST", "PORT", "NAME", "USERNAME", "PASSWORD"):
        value = os.getenv(f"DB_{key}")
        if value:
            os.environ.setdefault(f"VECTOR_DB_{key}", value)

    # Cloud Run reaches Cloud SQL over a unix socket. Cognee builds its URL from DB_HOST and
    # DB_PORT, which cannot express a socket, so it travels as a connect arg instead.
    if PROFILE == "cloud" and os.getenv("K_SERVICE"):
        instance = os.environ["CLOUDSQL_INSTANCE"]
        os.environ["DATABASE_CONNECT_ARGS"] = json.dumps({"host": f"/cloudsql/{instance}"})
