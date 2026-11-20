# Paths, folder roles, the exclusion list, and the guards that fail a bad setup at start.
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Graphify's raw graph.json, kept out of the folder being mapped
_graph_dir = os.getenv("PMB_GRAPH_DIR", "")
GRAPH_DIR = (
    Path(_graph_dir) if Path(_graph_dir).is_absolute() else REPO_ROOT / (_graph_dir or "graph")
).resolve()

# The one Obsidian vault every brain generates into; a digested folder is only ever read
DOCS = (
    Path(os.environ["PMB_DOCS"]).resolve()
    if os.getenv("PMB_DOCS")
    else (REPO_ROOT.parent / "docs").resolve()
)

# Where compose mounts PMB_WORKSPACE, read-only
WORKSPACE = Path(os.getenv("PMB_WORKSPACE_MOUNT", "/workspace"))

GENERATED = "graph"
GENERATED_SUBDIRS = ("code",)
HUMAN = "memory"

# A folder's role, one word in a .pmb file inside it
MARKER = ".pmb"
ROLES = ("root", "brain")

# pgvector builds no HNSW or IVFFlat index wider than this, and does not say so
MAX_INDEXABLE_DIMENSIONS = 2000

# auto, exact, ivfflat or hnsw; HNSW wants about 4 GiB to build
INDEX_KIND = os.getenv("PMB_INDEX", "auto")
FLAT_THRESHOLD = int(os.getenv("PMB_INDEX_THRESHOLD", "10000"))

# Embedding providers that run on this machine and need no key
LOCAL_PROVIDERS = frozenset({"ollama"})
OLLAMA_ENDPOINT = "http://host.docker.internal:11434/api/embed"

DOCUMENT_SUFFIXES = frozenset({".md"})

# Never read, whatever folder the tool is pointed at
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
        GENERATED,
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

_GIT_BASH_DRIVE = re.compile(r"^/([a-zA-Z])/")
_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:/")


def namespace(target: Path) -> str:
    """The memory name for a folder: its directory name, lowercased."""
    target = target.resolve()
    # The mount point erases the workspace's own name, so take it from the host path
    if target == WORKSPACE.resolve() and os.getenv("PMB_WORKSPACE"):
        target = Path(_normalise(os.environ["PMB_WORKSPACE"]))
    name = target.name.lower()
    if not name:
        raise ValueError(f"cannot derive a name from {target}")
    return name


def generated_path(kind: str, name: str, *parts: str) -> Path:
    """A path under the vault's generated area, refusing to escape it into `memory/`."""
    if kind not in GENERATED_SUBDIRS:
        raise ValueError(f"unknown generated kind {kind!r}. Use one of: {GENERATED_SUBDIRS}")
    root = (DOCS / GENERATED / kind).resolve()
    path = root.joinpath(name, *parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"refusing to write outside {root}: {path}")
    return path


def is_excluded(path: Path) -> bool:
    """True when a path must never be sent to the embedding model.

    ponytail: name and directory matching only, so a secret pasted into an ordinary .md still
    gets through. Add a content scan here if that stops being an acceptable risk.
    """
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_NAMES)


def collect_documents(root: Path) -> tuple[list[Path], list[Path]]:
    """The markdown to digest, and the files refused that a person would want to hear about."""
    root = root.resolve()
    included: list[Path] = []
    skipped: list[Path] = []
    for directory, subdirs, files in os.walk(root):
        # Pruned, never walked: node_modules and .git are most of a repository. keys/ is
        # walked so what it holds is reported
        subdirs[:] = sorted(d for d in subdirs if d not in EXCLUDED_DIRS or d == "keys")
        for name in sorted(files):
            path = Path(directory) / name
            document = path.suffix.lower() in DOCUMENT_SUFFIXES
            if not is_excluded(path):
                if document:
                    included.append(path)
            elif document or any(fnmatch.fnmatch(name, p) for p in EXCLUDED_NAMES):
                skipped.append(path)
    return included, skipped


def role_of(target: Path) -> str | None:
    """`root`, `brain`, or None for a folder that was never initialised."""
    marker = target / MARKER
    if not marker.is_file():
        return None
    value = marker.read_text(encoding="utf-8").strip().lower()
    return value if value in ROLES else None


def children(root: Path) -> list[Path]:
    """The folders a root digests, brains first, because everything else is read against them."""
    found = [
        path
        for path in sorted(root.iterdir())
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in EXCLUDED_DIRS
        and collect_documents(path)[0]
    ]
    return sorted(found, key=lambda path: role_of(path) != "brain")


def _normalise(path: str) -> str:
    """Forward slashes, no trailing slash, and Git Bash `/c/x` as `c:/x`."""
    path = path.strip().replace("\\", "/")
    path = _GIT_BASH_DRIVE.sub(lambda match: f"{match[1]}:/", path, count=1)
    return path.rstrip("/") if len(path) > 1 else path


def _under(path: str, root: str) -> bool:
    # Windows paths compare case-insensitively
    if _WINDOWS_DRIVE.match(root + "/"):
        path, root = path.lower(), root.lower()
    return path == root or path.startswith(root + "/")


def resolve_folder(path: str, host_root: str | None = None, mount: Path | None = None) -> Path:
    """Map a folder as the agent names it on the host to where the server sees it.

    Takes an absolute host path in Windows, Git Bash or POSIX form, a path relative to the
    workspace, or a path already under the mount.
    """
    host_root = os.getenv("PMB_WORKSPACE", "") if host_root is None else host_root
    mount = WORKSPACE if mount is None else mount
    given, root, inside = _normalise(path), _normalise(host_root), mount.as_posix()
    if not given:
        raise ValueError("name a folder: its path on this machine, or its path in the workspace")

    if given == inside or given.startswith(inside + "/"):
        relative = given[len(inside) :]
    elif root and _under(given, root):
        relative = given[len(root) :]
    elif given.startswith("/") or _WINDOWS_DRIVE.match(given + "/"):
        raise ValueError(
            f"{path} is outside PMB_WORKSPACE ({host_root or 'not set'}), the only folder the "
            "server can read. Move the folder under it, or widen PMB_WORKSPACE and restart."
        )
    else:
        relative = given

    resolved = (mount / relative.lstrip("/")).resolve()
    if not resolved.is_relative_to(mount.resolve()):
        raise ValueError(f"refusing {path}: it leaves the workspace")
    if not resolved.is_dir():
        raise ValueError(f"not a folder in the workspace: {path}")
    return resolved


def db_connect_kwargs() -> dict[str, object]:
    """asyncpg connection arguments."""
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ["DB_USERNAME"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
    }


def embedding_signature() -> str:
    """Which model built the vectors. Two models in one database rank each other wrong."""
    return ":".join(
        os.environ.get(key, "")
        for key in ("EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS")
    )


def configure() -> None:
    """Load `.env`, set the invariants, and fail fast on a bad setup.

    Must run before `import cognee`, which reads its settings from the environment at import.
    """
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    os.environ.setdefault("DB_PROVIDER", "postgres")
    os.environ.setdefault("VECTOR_DB_PROVIDER", "pgvector")
    os.environ.setdefault("GRAPH_DATABASE_PROVIDER", "postgres")
    os.environ.setdefault("TELEMETRY_DISABLED", "1")
    # One person's brain: cognee's per-user databases make `add` fail on a dead connection
    os.environ.setdefault("REQUIRE_AUTHENTICATION", "false")
    os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
    # cognee's 30s pre-flight check times out against providers that answer in milliseconds
    os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")

    required = (
        "DB_HOST",
        "DB_NAME",
        "DB_USERNAME",
        "DB_PASSWORD",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit(
            f"missing in .env: {', '.join(missing)}. Copy .env.example and fill it in."
        )

    provider = os.environ["EMBEDDING_PROVIDER"].lower()
    if provider in LOCAL_PROVIDERS:
        if not os.getenv("EMBEDDING_ENDPOINT"):
            os.environ["EMBEDDING_ENDPOINT"] = OLLAMA_ENDPOINT
    elif not os.getenv("EMBEDDING_API_KEY"):
        raise SystemExit(
            f"EMBEDDING_API_KEY is not set, and {provider} is an API. Set it, or use "
            "EMBEDDING_PROVIDER=ollama to embed on this machine."
        )

    dimensions = int(os.getenv("EMBEDDING_DIMENSIONS") or "1024")
    os.environ["EMBEDDING_DIMENSIONS"] = str(dimensions)
    if dimensions > MAX_INDEXABLE_DIMENSIONS:
        raise SystemExit(
            f"EMBEDDING_DIMENSIONS={dimensions} exceeds {MAX_INDEXABLE_DIMENSIONS}, the widest "
            "vector pgvector will index. Every search would be a sequential scan. Use 1024."
        )

    if INDEX_KIND not in ("auto", "exact", "ivfflat", "hnsw"):
        raise SystemExit(f"PMB_INDEX={INDEX_KIND!r}. Use auto, exact, ivfflat or hnsw.")

    # The vector store is the same Postgres: one database, one backup
    for key in ("HOST", "PORT", "NAME", "USERNAME", "PASSWORD"):
        value = os.getenv(f"DB_{key}")
        if value:
            os.environ.setdefault(f"VECTOR_DB_{key}", value)
