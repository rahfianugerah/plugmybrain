# The single entry point. Three commands, and printing lives here so every other module
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
    """Build a Graphify code map and copy its report into the folder's graph/ area.

    Returns None when there is nothing to map, which a folder of pure markdown always is.
    `--code-only` keeps every file on the local tree-sitter path: no API key, nothing uploaded.
    """
    exe = _graphify()
    if exe is None:
        return None

    out_parent = config.GRAPH_DIR / config.namespace(target)
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

    destination = config.generated_path(target, "code", "GRAPH_REPORT.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, destination)
    return destination


async def digest(target: Path, dry_run: bool = False) -> None:
    from plugmybrain import export as export_module
    from plugmybrain import ingest as ingest_module

    config.configure()
    name = config.namespace(target)

    report = await ingest_module.ingest(target, dataset=name, dry_run=dry_run)

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

    if dry_run:
        print(f"estimate: {report.estimate}")
        print("\nNothing was spent. Drop --dry-run to digest for real.")
        return

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

    graph = await export_module.export(target)
    print(f"graph:    {graph.written} of {graph.total} note(s) in {graph.directory}")
    if graph.dropped:
        print(f"          {graph.dropped} less-connected node(s) dropped")
    print(f"\nOpen {target} in Obsidian to see it.")


def _print_status(status) -> None:
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
    print(f"database:  {status.database} ({status.size}), {status.chunks} chunk(s) embedded")
    if not status.datasets:
        print("           empty. Nothing has been digested yet.")
        return
    width = max(len(d.name) for d in status.datasets)
    for row in status.datasets:
        here = "  <- this folder" if row.name == status.name else ""
        print(f"           {row.name:<{width}}  {row.documents:>4} doc(s)  {row.created}{here}")


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

    digest_cmd = sub.add_parser(
        "digest", help="turn a folder's markdown into memory, a code map and a graph"
    )
    target_argument(digest_cmd)
    digest_cmd.add_argument("--dry-run", action="store_true", help="estimate the cost and stop")

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

    if args.command == "digest":
        asyncio.run(digest(target, dry_run=args.dry_run))
        return 0

    if args.command == "list":
        from plugmybrain import manage

        _print_status(asyncio.run(manage.status(target)))
        return 0

    if args.command == "reset":
        from plugmybrain import manage

        scope = "EVERY folder's memory" if args.everything else f"the memory for {target.name}"
        # Confirmed rather than assumed: this is the only destructive command, and a digest of a
        # large folder costs real money to rebuild even though nothing is truly lost.
        if not args.yes:
            print(f"About to delete {scope} from the database, and {target / config.GENERATED}.")
            print(f"{target / config.HUMAN} and every other markdown file are left alone.")
            if input("Type yes to continue: ").strip().lower() != "yes":
                print("Nothing was deleted.")
                return 1

        report = asyncio.run(manage.reset(target, everything=args.everything))
        count = "all" if report.documents < 0 else str(report.documents)
        print(f"deleted:  {count} document(s) from the memory ({report.scope})")
        print(f"deleted:  {report.generated}")
        print(f"kept:     {report.kept if report.kept else 'every markdown file in the folder'}")
        print("\nRun `pmb digest` to build it again from the markdown.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
