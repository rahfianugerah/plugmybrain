# The one module that writes into the human-authored memory. Everything else in this project
# writes only to the generated area, which is why this guard sits alone in its own file.
#
# Generated notes are disposable: the next rebuild overwrites them and git ignores them. When
# one turns out to be worth keeping, promoting it makes it yours. It gains the five-key
# frontmatter, it is committed, you can edit it freely, and `pmb sync` ingests it into the
# `curated` dataset, which wins on conflict with anything a machine inferred.
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from plugmybrain import config

# Lines a generated note carries that a human-authored one must not: the breadcrumb, and the
# warning that the file is disposable. Both are false the moment it is promoted.
_STRIP = (
    re.compile(r"^> Up: .*$", re.M),
    re.compile(r"^Generated from the .*?overwrites this file\.\s*$", re.M | re.S),
    re.compile(r"^## Related\s*\n(?:- \[\[graph/README\.md\]\]\s*\n?)+", re.M),
)


@dataclass
class PromoteReport:
    source: Path
    destination: Path
    title: str
    note_type: str


def slug(text: str) -> str:
    """A kebab-case filename from a title, per memory.rules.md."""
    return (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "note")[:60]


def _title_of(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.M)
    return match.group(1).strip() if match else fallback


def promote(
    source: Path,
    note_type: str = "fact",
    title: str | None = None,
    tags: list[str] | None = None,
    force: bool = False,
) -> PromoteReport:
    """Copy a generated note into the human-authored memory, with the required frontmatter."""
    source = source.resolve()
    if not source.is_file():
        raise SystemExit(f"no such file: {source}")

    # Only the generated area can be promoted. Without this, `pmb promote` becomes a way to
    # write an arbitrary file into the memory, which is the human's area alone.
    generated = config.VAULT_GENERATED.resolve()
    if not source.is_relative_to(generated):
        raise SystemExit(
            f"{source} is not under {generated}.\n"
            "Only a generated note can be promoted. Write anything else into the memory yourself."
        )

    # utf-8-sig, not utf-8: a BOM written by a Windows editor sits before the first character
    # and silently defeats every `^` anchor below, so the breadcrumb survives into the memory.
    text = source.read_text(encoding="utf-8-sig")
    for pattern in _STRIP:
        text = pattern.sub("", text)
    body = re.sub(r"\n{3,}", "\n\n", text).strip()

    heading = title or _title_of(body, source.stem.replace("-", " "))
    body = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.M)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    destination = config.memory_path(note_type, f"{slug(heading)}.md")
    if destination.exists() and not force:
        raise SystemExit(
            f"{destination} already exists. That is a human-authored note; it is not overwritten "
            "without --force."
        )

    today = date.today().isoformat()
    label = ", ".join(tags or [source.parent.name])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "---\n"
        f"type: {note_type}\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"tags: [{label}]\n"
        "status: current\n"
        "---\n"
        "\n"
        f"# {heading}\n"
        "\n"
        f"{body}\n"
        "\n"
        "**Why:** [promoted from the generated graph. Say why it is worth keeping, or this note "
        "is just a machine's guess with a date on it.]\n"
        "\n"
        "Related: [[graph/README.md]]\n",
        encoding="utf-8",
    )
    return PromoteReport(source=source, destination=destination, title=heading, note_type=note_type)
