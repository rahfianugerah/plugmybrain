# Paths and profile. One module for both profiles; BRAIN_PROFILE is the only switch.
from __future__ import annotations

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
