# The single entry point. Printing lives here; every other module returns data instead.
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from plugmybrain import config, retrieve


def _graphify() -> str:
    exe = shutil.which("graphify")
    if exe is None:
        raise SystemExit(
            "graphify not found. Activate the `env` conda environment, then: pip install graphifyy"
        )
    return exe


def map_folder(target: Path) -> tuple[Path, Path]:
    """Build a code map for `target`. Returns (graph.json, the report copied into the vault).

    Writes only under PMB_GRAPH_DIR and the vault's generated area, never into `target`.
    """
    target = target.resolve()
    if not target.is_dir():
        raise SystemExit(f"not a directory: {target}")

    name = config.namespace(target)
    out_parent = config.GRAPH_DIR / name
    out_parent.mkdir(parents=True, exist_ok=True)

    # --code-only keeps every file on the local tree-sitter path: no API key, nothing uploaded.
    # graphify writes <out_parent>/graphify-out/ and honours the target's .gitignore by default.
    # extract is incremental on its own manifest, so a re-run only re-reads what changed.
    result = subprocess.run(
        [_graphify(), "extract", str(target), "--code-only", "--out", str(out_parent)],
    )
    if result.returncode != 0:
        raise SystemExit(
            f"graphify failed on {target}.\n"
            "A folder with no source files is the usual cause: --code-only indexes code only, "
            "so a documentation or markdown folder produces an empty graph. "
            "Documents belong to `pmb ingest`, not `pmb map`."
        )

    produced = out_parent / "graphify-out"
    graph = produced / "graph.json"
    if not graph.is_file():
        raise SystemExit(f"graphify produced no graph at {graph}")

    # `extract` writes graph.json only. GRAPH_REPORT.md and graph.html come from clustering,
    # and --no-label keeps community naming off the LLM, so the whole map stays at zero tokens.
    subprocess.run([_graphify(), "cluster-only", str(out_parent), "--no-label"], check=True)

    report = produced / "GRAPH_REPORT.md"
    if not report.is_file():
        raise SystemExit(f"graphify produced no report at {report}")

    destination = config.generated_path("code", name, "GRAPH_REPORT.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, destination)
    return graph, destination


def _print_ingest(report) -> None:
    print(f"dataset:  {report.dataset}")
    print(f"ingested: {report.ingested} document(s)")
    print(f"skipped:  {len(report.skipped)} file(s) by the exclusion list")
    for path in report.skipped[:10]:
        print(f"          {path}")
    if len(report.skipped) > 10:
        print(f"          ... and {len(report.skipped) - 10} more")
    if report.estimate is not None:
        print(f"estimate: {report.estimate}")
    for created in report.indexes_created:
        print(f"indexed:  {created}")
    for small in report.indexes_skipped:
        print(f"exact:    {small}")
    for due in report.indexes_rebuild_due:
        print(f"REBUILD:  {due}. Drop the index and re-run to resize it")
    for refused in report.indexes_refused:
        print(f"REFUSED:  {refused} did not match the identifier allowlist and was left unindexed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmb", description="PlugMyBrain - Plug & play memory for your AI agents."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    map_cmd = sub.add_parser("map", help="build a Graphify code map for a folder")
    map_cmd.add_argument("target", type=Path, help="the folder to map")

    ingest_cmd = sub.add_parser("ingest", help="ingest a folder's documents into its own dataset")
    ingest_cmd.add_argument("target", type=Path, help="the folder to ingest")
    ingest_cmd.add_argument(
        "--dry-run", action="store_true", help="estimate the cognify cost and stop"
    )
    ingest_cmd.add_argument("--memify", action="store_true", help="run the extra enrichment pass")

    sync_cmd = sub.add_parser("sync", help="re-ingest the curated rules and memory")
    sync_cmd.add_argument(
        "--dry-run", action="store_true", help="estimate the cognify cost and stop"
    )

    search_cmd = sub.add_parser("search", help="search one dataset")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--project", required=True, help="the dataset to search")
    search_cmd.add_argument("--mode", default="chunks", choices=list(retrieve.MODES))
    search_cmd.add_argument("--top-k", type=int, default=15)

    export_cmd = sub.add_parser("export", help="render the knowledge graph as vault notes")
    export_cmd.add_argument("--project", required=True, help="the dataset to export")
    export_cmd.add_argument("--limit", type=int, default=500, help="most-connected nodes to write")

    note_cmd = sub.add_parser(
        "note", help="write a memory note; the body is read from stdin"
    )
    note_cmd.add_argument("title", help="states the thing, not the topic")
    note_cmd.add_argument("--type", default="session", choices=list(config.NOTE_TYPES))
    note_cmd.add_argument("--tags", help="comma-separated, defaults to the note type")
    note_cmd.add_argument("--force", action="store_true", help="overwrite an existing note")

    promote_cmd = sub.add_parser(
        "promote", help="keep a generated note: copy it into the human-authored memory"
    )
    promote_cmd.add_argument("source", type=Path, help="a note under the vault's graph/ area")
    promote_cmd.add_argument("--type", default="fact", choices=list(config.NOTE_TYPES))
    promote_cmd.add_argument("--title", help="override the note's title")
    promote_cmd.add_argument("--tags", help="comma-separated, defaults to the dataset name")
    promote_cmd.add_argument("--force", action="store_true", help="overwrite an existing note")

    viz_cmd = sub.add_parser("visualize", help="render the knowledge graph as one HTML file")
    viz_cmd.add_argument("--project", required=True, help="the dataset to render")
    viz_cmd.add_argument("--max-nodes", type=int, default=500)

    eval_cmd = sub.add_parser("eval", help="score the question set and time the warm path")
    eval_cmd.add_argument("--project", default=config.CURATED_DATASET)

    serve_cmd = sub.add_parser("serve", help="run the HTTP API locally")
    serve_cmd.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args(argv)

    if args.command == "map":
        graph, report = map_folder(args.target)
        print(f"graph:  {graph}")
        print(f"report: {report}")
        return 0

    if args.command in ("ingest", "sync"):
        from plugmybrain import ingest as ingest_module

        if args.command == "sync":
            paths, dataset = list(config.CURATED_PATHS), config.CURATED_DATASET
        else:
            paths, dataset = [args.target], config.namespace(args.target)
        report = asyncio.run(
            ingest_module.ingest(
                paths,
                dataset=dataset,
                dry_run=args.dry_run,
                memify=getattr(args, "memify", False),
            )
        )
        _print_ingest(report)
        return 0

    if args.command == "search":
        results = asyncio.run(
            retrieve.search(args.query, dataset=args.project, mode=args.mode, top_k=args.top_k)
        )
        print(f"sources: {', '.join(retrieve.sources(results)) or 'none cited'}")
        for item in results:
            print(item)
        return 0

    if args.command == "export":
        from plugmybrain import export as export_module

        report = asyncio.run(export_module.export(args.project, limit=args.limit))
        print(f"wrote {report.written} of {report.total} node(s) to {report.directory}")
        if report.dropped:
            print(
                f"dropped {report.dropped} less-connected node(s). Raise --limit to include them."
            )
        return 0

    if args.command == "note":
        from plugmybrain import promote as promote_module

        body = sys.stdin.read() if not sys.stdin.isatty() else ""
        report = promote_module.write_note(
            args.title,
            body,
            note_type=args.type,
            tags=[t.strip() for t in args.tags.split(",")] if args.tags else None,
            force=args.force,
        )
        print(f"wrote: {report.destination}")
        print("Run `pmb sync` to fold it into the memory.")
        return 0

    if args.command == "promote":
        from plugmybrain import promote as promote_module

        report = promote_module.promote(
            args.source,
            note_type=args.type,
            title=args.title,
            tags=[t.strip() for t in args.tags.split(",")] if args.tags else None,
            force=args.force,
        )
        print(f"promoted: {report.destination}")
        print("It is yours now: committed, editable, and ingested as `curated` on the next sync.")
        print("Fill in the Why line, then run: pmb sync")
        return 0

    if args.command == "visualize":
        from plugmybrain import export as export_module

        path = asyncio.run(export_module.visualize(args.project, max_nodes=args.max_nodes))
        print(f"open: {path}")
        return 0

    if args.command == "eval":
        from plugmybrain import eval as eval_module

        report = asyncio.run(eval_module.run(dataset=args.project))
        for answer in report.answers:
            mark = "ok  " if answer.hit else "MISS"
            hop = " [multi-hop]" if answer.multihop else ""
            print(f"{mark} {answer.seconds:6.2f}s  {answer.question}{hop}")
            if not answer.hit:
                print(f"      expected {answer.expected}, cited {answer.found or 'nothing'}")
        print(f"\nscore: {report.score}   p50: {report.p50:.2f}s   p95: {report.p95:.2f}s")
        print("No Cloud Run cold start is on this path in either profile.")
        return 0

    if args.command == "serve":
        import uvicorn

        # Cloud Run injects PORT and the container must read it rather than hardcode 8080.
        uvicorn.run("plugmybrain.api:app", host=args.host, port=int(os.getenv("PORT", "8080")))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
