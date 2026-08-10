# The single entry point. Phase 1 implements `map`; ingest, search, export and eval land in Phase 2.
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from brain import config


def _graphify() -> str:
    exe = shutil.which("graphify")
    if exe is None:
        raise SystemExit(
            "graphify not found. Activate the `env` conda environment, then: pip install graphifyy"
        )
    return exe


def map_folder(target: Path) -> tuple[Path, Path]:
    """Build a code map for `target`. Returns (graph.json, the report copied into the vault).

    Writes only under BRAIN_GRAPH_DIR and the vault's generated area, never into `target`.
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
            "Documents belong to `brain ingest`, not `brain map`."
        )

    produced = out_parent / "graphify-out"
    graph = produced / "graph.json"
    if not graph.is_file():
        raise SystemExit(f"graphify produced no graph at {graph}")

    # `extract` writes graph.json only. GRAPH_REPORT.md and graph.html come from clustering,
    # and --no-label keeps community naming off the LLM, so the whole map stays at zero tokens.
    subprocess.run(
        [_graphify(), "cluster-only", str(out_parent), "--no-label"],
        check=True,
    )

    report = produced / "GRAPH_REPORT.md"
    if not report.is_file():
        raise SystemExit(f"graphify produced no report at {report}")

    destination = config.generated_path("code", name, "GRAPH_REPORT.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, destination)
    return graph, destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain", description="Plug-and-play memory brain.")
    sub = parser.add_subparsers(dest="command", required=True)

    map_cmd = sub.add_parser("map", help="build a Graphify code map for a folder")
    map_cmd.add_argument("target", type=Path, help="the folder to map")

    args = parser.parse_args(argv)

    if args.command == "map":
        graph, report = map_folder(args.target)
        print(f"graph:  {graph}")
        print(f"report: {report}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
