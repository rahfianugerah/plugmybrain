# The MCP server, and the whole of PlugMyBrain as an agent sees it: six tools.
# Reads answer from Postgres and the code map; writes touch the index and the vault only.
from __future__ import annotations

import asyncio
import os
import re
import shutil

from plugmybrain import config, jobs, manage, retrieve

INSTRUCTIONS = "\n\n".join(
    [
        "PlugMyBrain is the memory for the folders on this machine.",
        "Call `recall` before answering anything about a project's rules, decisions, "
        "architecture or history, and `code_map` before searching a codebase for where "
        "something lives. A brain is a folder's own name, lowercased; `brains` lists them.",
        "The memory is markdown on disk. To remember something, write a note into the folder's "
        "`memory/` with your own file tools, then call `digest` on that folder. Nothing here "
        "writes into a project.",
    ]
)

# Under Codex's 60 second default tool timeout
WAIT = 45

_BRAIN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


async def _run(action: str, target, wait_seconds: int, *flags: str) -> str:
    """Start a job, or keep waiting on the same one, and report it once it ends."""
    job = jobs.current()
    same = job is not None and (job.action, job.target) == (action, str(target))
    if job and job.running and not same:
        return f"Busy: {job.action} of {job.target} is running. Wait for it, then try again."
    if not (same and (job.running or not job.reported)):
        job = await jobs.start(action, target, *flags)

    if not await jobs.wait(job, min(max(wait_seconds, 0), 600)):
        return (
            f"{action} of {target} is still running after {job.elapsed}s. Call `{action}` "
            f"again with the same folder to keep waiting.\n\n{jobs.output(2000)}"
        )
    job.reported = True
    return f"{action} of {target} {job.outcome} in {job.elapsed}s.\n\n{jobs.output()}"


def _job_line() -> str:
    job = jobs.current()
    if job is None:
        return "job:       none since the server started"
    return f"job:       {job.action} of {job.target}, {job.outcome}, {job.elapsed}s"


def build():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name="plugmybrain", instructions=INSTRUCTIONS)

    @server.tool(
        description=(
            "Search a folder's memory and return the passages, each with the file it came "
            "from. `brain` is the folder name lowercased, or several separated by commas when "
            "a question spans projects: the standards brain plus the service it asks about."
        )
    )
    async def recall(query: str, brain: str, top_k: int = 15) -> str:
        try:
            results = await retrieve.search(query, brain=brain, top_k=top_k)
        except ValueError as error:
            return str(error)
        if not results:
            return (
                f"Nothing in {brain} matches that. Say so rather than answering from general "
                "knowledge; an unsourced answer that looks sourced is worse than an empty one."
            )
        lines = [f"sources: {', '.join(retrieve.sources(results))}", ""]
        for item in results:
            lines.append(f"--- {item.get('document_name') or '?'}\n{item.get('text') or ''}")
        return "\n".join(lines)

    @server.tool(
        description=(
            "List every brain on this machine and how many documents each holds. Use it to "
            "find the right name for `recall`, or when the user switches brain mid-session."
        )
    )
    async def brains() -> str:
        found = await retrieve.brains()
        if not found:
            return "No brain has been digested yet. Run /pmb-digest in a folder first."
        width = max(len(name) for name, _ in found)
        return "\n".join(f"{name:<{width}}  {count} document(s)" for name, count in found)

    @server.tool(
        description=(
            "Show what a folder holds against what was digested, every memory in the database, "
            "the embedding model, and the running job. `folder` is its path on this machine; "
            "leave it empty for the database alone."
        )
    )
    async def status(folder: str = "") -> str:
        try:
            target = config.resolve_folder(folder) if folder.strip() else None
        except ValueError as error:
            return str(error)
        return f"{await manage.describe(target)}\n{_job_line()}"

    @server.tool(
        description=(
            "Digest a folder: chunk and embed its markdown into the memory named after it, and "
            "map its source code with Graphify. A root folder digests every child, brains "
            "first. Runs in the background and returns the report once it ends; if it is "
            "still running after `wait_seconds`, call again with the same folder to keep waiting."
        )
    )
    async def digest(folder: str, wait_seconds: int = WAIT) -> str:
        try:
            target = config.resolve_folder(folder)
        except ValueError as error:
            return str(error)
        return await _run("digest", target, wait_seconds)

    @server.tool(
        description=(
            "Delete a folder's memory from the database and its generated notes. Markdown is "
            "never touched, so a digest rebuilds it. Ask the user first, then pass `confirm` "
            "as the brain name, or as `everything` with everything=true to empty the database."
        )
    )
    async def reset(folder: str = "", confirm: str = "", everything: bool = False) -> str:
        try:
            target = (
                config.WORKSPACE
                if everything and not folder.strip()
                else config.resolve_folder(folder)
            )
        except ValueError as error:
            return str(error)
        expected = "everything" if everything else config.namespace(target)
        if confirm.strip().lower() != expected:
            return f"Nothing was reset. Ask the user, then call again with confirm={expected!r}."
        flags = ("--yes", "--all") if everything else ("--yes",)
        return await _run("reset", target, WAIT, *flags)

    @server.tool(
        description=(
            "Ask a folder's code map, which Graphify built from the source with no model. "
            "With a question, the code that answers it and how it connects; without one, the "
            "most connected parts of the codebase. `brain` is the folder name lowercased."
        )
    )
    async def code_map(brain: str, question: str = "") -> str:
        name = brain.strip().lower()
        if not _BRAIN.match(name):
            return "`brain` is one folder name, such as plugmybrain."
        graph = config.GRAPH_DIR / name / "graphify-out" / "graph.json"
        if not graph.is_file():
            return (
                f"No code map for {name}. Digest it first; a folder with no source code has none."
            )
        exe = shutil.which("graphify")
        if exe is None:
            return "Graphify is not installed where this server runs."
        args = ["query", question, "--budget", "2000"] if question.strip() else ["god-nodes"]
        process = await asyncio.create_subprocess_exec(
            exe,
            *args,
            "--graph",
            str(graph),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        except TimeoutError:
            process.kill()
            return "Graphify did not answer within 60 seconds."
        return out.decode("utf-8", errors="replace").strip() or "Graphify found nothing for that."

    return server


def main() -> None:
    # Before cognee is imported anywhere: it reads its settings at import
    config.configure()
    build().run(
        transport="streamable-http",
        host=os.getenv("PMB_HOST", "0.0.0.0"),
        port=int(os.getenv("PMB_PORT", "8000")),
        streamable_http_path="/mcp",
    )


if __name__ == "__main__":
    main()
