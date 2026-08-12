# The single entry point. Four commands, and printing lives here so every other module
# returns data instead.
from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from plugmybrain import config


def _graphify() -> str | None:
    """The graphify executable, or None. Missing is not fatal: the code map is the free half of
    a digest and the memory is the half that matters."""
    return shutil.which("graphify")


def map_code(target: Path) -> Path | None:
    """Build a Graphify code map and copy its report into the vault, under this brain's name.

    Returns None when there is nothing to map, which a folder of pure markdown always is.
    `--code-only` keeps every file on the local tree-sitter path: no API key, nothing uploaded.
    """
    exe = _graphify()
    if exe is None:
        return None

    name = config.namespace(target)
    out_parent = config.GRAPH_DIR / name
    out_parent.mkdir(parents=True, exist_ok=True)

    # extract is incremental on its own manifest, so a re-run only re-reads what changed.
    extract = subprocess.run([exe, "extract", str(target), "--code-only", "--out", str(out_parent)])
    if extract.returncode:
        return None

    # extract writes graph.json only; the report comes from clustering. --no-label keeps
    # community naming off the model, so the whole map stays at zero tokens.
    subprocess.run([exe, "cluster-only", str(out_parent), "--no-label"])

    report = out_parent / "graphify-out" / "GRAPH_REPORT.md"
    if not report.is_file():
        return None

    destination = config.generated_path("code", name, "GRAPH_REPORT.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, destination)
    return destination


async def digest(target: Path) -> None:
    """Digest one folder, or every child of a root."""
    from plugmybrain import bootstrap

    config.configure()

    if bootstrap.role_of(target) == "root":
        folders = bootstrap.children(target)
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
    from plugmybrain import ingest as ingest_module

    name = config.namespace(target)
    report = await ingest_module.ingest(target, dataset=name)

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
        print(f"REBUILD:  {due}. Drop the index and re-run to resize it")
    for refused in report.indexes_refused:
        print(f"REFUSED:  {refused} did not match the identifier allowlist and was left unindexed")

    code = map_code(target)
    print(f"code map: {code if code else 'none, no source files found'}")
    print(f"\nOpen {config.DOCS} in Obsidian to see it.")


def _print_folder(status) -> None:
    print(f"folder:    {status.target}")
    print(f"memory:    {status.name}")
    print()
    print(f"markdown in the folder:   {status.markdown}")
    print(f"  of which memory/:       {status.human_notes} (human-authored, survives a reset)")
    print(f"  digested into Cognee:   {status.ingested}")
    print(f"  generated into graph/:  {status.generated_notes} (rebuilt by digest)")
    print(f"  skipped as a secret:    {status.skipped}")
    if status.markdown != status.ingested:
        print(f"  -> {status.markdown - status.ingested} not digested. Run `pmb digest`.")
    print()


def _print_database(status, highlight: set[str]) -> None:
    print(f"database:  {status.database} ({status.size}), {status.chunks} chunk(s) embedded")
    if not status.datasets:
        print("           empty. Nothing has been digested yet.")
        return
    width = max(len(d.name) for d in status.datasets)
    for row in status.datasets:
        here = "  <-" if row.name in highlight else ""
        print(f"           {row.name:<{width}}  {row.documents:>4} doc(s)  {row.created}{here}")


def _print_child(status) -> None:
    """One line per child of a root. The gap between written and digested is the whole point."""
    gap = "" if status.markdown == status.ingested else f"  ({status.markdown} not digested)"
    if status.markdown == status.ingested and status.markdown:
        gap = "  up to date"
    print(f"  {status.name:<26} {status.ingested:>4} of {status.markdown:>4} markdown{gap}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmb",
        description="PlugMyBrain - a plug-and-play AI memory for any folder of markdown.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def target_argument(command):
        command.add_argument(
            "target", type=Path, nargs="?", default=Path.cwd(), help="the folder, default here"
        )

    init_cmd = sub.add_parser(
        "init", help="give a folder its role and wire the agents to the brain"
    )
    init_cmd.add_argument(
        "role", choices=["root", "brain"], help="root holds many projects; brain holds the rules"
    )
    target_argument(init_cmd)

    digest_cmd = sub.add_parser(
        "digest", help="turn a folder's markdown into memory, plus a code map"
    )
    target_argument(digest_cmd)

    reset_cmd = sub.add_parser("reset", help="throw away the derived memory, never the markdown")
    target_argument(reset_cmd)
    reset_cmd.add_argument(
        "--all", action="store_true", dest="everything", help="every folder, not just this one"
    )
    reset_cmd.add_argument("--yes", action="store_true", help="skip the confirmation")

    list_cmd = sub.add_parser("list", help="what the memory holds, and what it was built from")
    target_argument(list_cmd)

    args = parser.parse_args(argv)
    target = args.target.resolve()
    if not target.is_dir():
        raise SystemExit(f"not a directory: {target}")

    if args.command == "init":
        from plugmybrain import bootstrap

        report = bootstrap.init(target, args.role)
        print(f"{report.target} is now a {report.role}.")
        for path in report.created:
            print(f"created:  {path}")
        for path in report.removed:
            print(f"removed:  {path}, no longer shipped by this project")
        for wired in report.wired:
            print(f"wired:    {wired}")
        for warning in report.warnings:
            print(f"WARNING:  {warning}")
        print("\nRestart Claude Code and Codex; both load commands and servers at start.")
        return 0

    if args.command == "digest":
        asyncio.run(digest(target))
        return 0

    if args.command == "list":
        from plugmybrain import bootstrap, manage

        if bootstrap.role_of(target) == "root":
            folders = bootstrap.children(target)
            print(f"root:      {target}\n")
            names = set()
            for path in folders:
                child = asyncio.run(manage.status(path))
                _print_child(child)
                names.add(child.name)
            print()
            _print_database(asyncio.run(manage.status(target, scan=False)), names)
            return 0

        status = asyncio.run(manage.status(target))
        _print_folder(status)
        _print_database(status, {status.name})
        return 0

    if args.command == "reset":
        from plugmybrain import bootstrap, manage

        folders = (
            bootstrap.children(target)
            if bootstrap.role_of(target) == "root" and not args.everything
            else [target]
        )
        if args.everything:
            scope = "EVERY folder's memory in the database"
        elif len(folders) > 1:
            scope = f"the memory for {len(folders)} folder(s) under {target.name}"
        else:
            scope = f"the memory for {target.name}"

        # Confirmed rather than assumed: this is the only destructive command, and a digest of a
        # large folder costs real money to rebuild even though nothing is truly lost.
        if not args.yes:
            print(f"About to delete {scope}, and their generated notes under")
            print(f"{config.DOCS / config.GENERATED}.")
            print("Every folder that was digested is untouched: nothing was ever written to it.")
            if input("Type yes to continue: ").strip().lower() != "yes":
                print("Nothing was deleted.")
                return 1

        for folder in folders:
            report = asyncio.run(manage.reset(folder, everything=args.everything))
            count = "all" if report.documents < 0 else str(report.documents)
            print(f"deleted:  {count} document(s) from the memory ({report.scope})")
            for path in report.generated:
                print(f"deleted:  {path}")
        print("\nEvery markdown file is untouched. Run `pmb digest` to build it again.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
