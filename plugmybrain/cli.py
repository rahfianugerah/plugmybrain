# What the server runs in the background, and the fallback for ops: digest, list, reset.
# Agents never call this directly; they use the MCP tools behind the /pmb-* commands.
from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from plugmybrain import config

_GRAPH_README = (
    "\n\n".join(
        [
            "# Graph",
            "Every brain on this machine generates into here, one folder per brain. A digest "
            "writes it and a reset deletes it, so editing anything below this file is wasted work.",
            "`code/<brain>/` holds the Graphify code map: the hubs, the connections, and the "
            "questions worth asking about a codebase, extracted by tree-sitter with no model.",
            "This README is not generated and is not deleted by a reset. When a generated note is "
            "worth keeping, move it into `memory/` and write down why.",
        ]
    )
    + "\n"
)


def ensure_vault() -> None:
    """The vault's graph/README.md, and graph/code/ in its .gitignore. Never overwrites."""
    readme = config.DOCS / config.GENERATED / "README.md"
    if not readme.exists():
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(_GRAPH_README, encoding="utf-8")

    gitignore = config.DOCS / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    if "graph/code/" not in existing:
        separator = "" if existing.endswith("\n") or not existing else "\n"
        gitignore.write_text(
            f"{existing}{separator}\n# PlugMyBrain, rebuilt by every digest\ngraph/code/\n",
            encoding="utf-8",
        )


def map_code(target: Path) -> str:
    """Build the Graphify code map, copy its report into the vault, and say what happened."""
    exe = shutil.which("graphify")
    if exe is None:
        return "skipped, graphify is not installed here"

    name = config.namespace(target)
    out_parent = config.GRAPH_DIR / name
    out_parent.mkdir(parents=True, exist_ok=True)

    # --code-only keeps it on local tree-sitter: no key, nothing uploaded
    extract = subprocess.run([exe, "extract", str(target), "--code-only", "--out", str(out_parent)])
    if extract.returncode:
        return "none, no source files found"

    # --no-label keeps community naming off a model, so the map costs nothing
    subprocess.run([exe, "cluster-only", str(out_parent), "--no-label", "--no-viz"])

    report = out_parent / "graphify-out" / "GRAPH_REPORT.md"
    if not report.is_file():
        return "none, no source files found"

    destination = config.generated_path("code", name, "GRAPH_REPORT.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, destination)
    return str(destination)


async def digest(target: Path) -> None:
    """Digest one folder, or every child of a root."""
    config.configure()
    ensure_vault()

    if config.role_of(target) == "root":
        folders = config.children(target)
        if not folders:
            raise SystemExit(f"no child folder under {target} holds any markdown.")
        print(f"root:     {target}")
        print(f"children: {', '.join(path.name for path in folders)}\n")
        for path in folders:
            await digest_one(path)
            print()
        return

    await digest_one(target)


async def digest_one(target: Path) -> None:
    from plugmybrain import ingest

    name = config.namespace(target)
    report = await ingest.ingest(target, dataset=name)

    print(f"folder:   {target}")
    print(f"memory:   {name}")
    print(f"markdown: {report.ingested} file(s) digested")
    print(f"skipped:  {len(report.skipped)} file(s) by the exclusion list")
    for path in report.skipped[:10]:
        print(f"          {path}")
    if len(report.skipped) > 10:
        print(f"          ... and {len(report.skipped) - 10} more")
    for dup in report.duplicates:
        print(f"duplicate: {dup}, digested once")
    for created in report.indexes_created:
        print(f"indexed:  {created}")
    for small in report.indexes_skipped:
        print(f"exact:    {small}")
    for due in report.indexes_rebuild_due:
        print(f"REBUILD:  {due}. Drop the index and digest again to resize it")
    for refused in report.indexes_refused:
        print(f"REFUSED:  {refused} did not match the identifier allowlist and was left unindexed")
    print(f"code map: {map_code(target)}")


async def reset(target: Path, everything: bool) -> None:
    from plugmybrain import manage

    config.configure()
    folders = (
        config.children(target) if config.role_of(target) == "root" and not everything else [target]
    )
    for folder in folders:
        report = await manage.reset(folder, everything=everything)
        count = "all" if report.documents < 0 else str(report.documents)
        print(f"deleted:  {count} document(s) from the memory ({report.scope})")
        for path in report.generated:
            print(f"deleted:  {path}")
    print("\nEvery markdown file is untouched. Digest the folder to build it again.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmb",
        description="PlugMyBrain internals. Agents use the MCP tools behind the /pmb-* commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("digest", "turn a folder's markdown into memory, plus a code map"),
        ("list", "what the memory holds, and what it was built from"),
        ("reset", "throw away the derived memory, never the markdown"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("target", type=Path, nargs="?", default=Path.cwd())
        if name == "reset":
            command.add_argument("--all", action="store_true", dest="everything")
            command.add_argument("--yes", action="store_true", help="skip the confirmation")

    args = parser.parse_args(argv)
    target = args.target.resolve()
    if not target.is_dir():
        raise SystemExit(f"not a directory: {target}")

    if args.command == "digest":
        asyncio.run(digest(target))
    elif args.command == "list":
        from plugmybrain import manage

        config.configure()
        print(asyncio.run(manage.describe(target)))
    else:
        # The one destructive command, so it asks unless told not to
        if (
            not args.yes
            and input(f"Delete the memory for {target.name}? Type yes: ").strip() != "yes"
        ):
            print("Nothing was deleted.")
            return 1
        asyncio.run(reset(target, args.everything))
    return 0


if __name__ == "__main__":
    sys.exit(main())
