# The MCP server, written here rather than taken from cognee-mcp.
#
# cognee-mcp exposes eleven tools: remember, recall, forget, cognify_file, create_dataset_json,
# list_datasets_json, list_dataset_data_json, get_client_info_json, upload_file_ui,
# open_cognee_workspace and visualize_graph_ui. Three of those write straight into the index,
# which the next digest silently overwrites; four are JSON dumps of things `pmb list` already
# prints; three open a browser UI that has no place in a coding agent's tool list. Every tool an
# agent can see costs context on every single turn, whether it is called or not.
#
# So this server exposes two, and neither can write anything.
from __future__ import annotations

import os

from plugmybrain import config, retrieve

INSTRUCTIONS = """PlugMyBrain is the memory for the folders on this machine.

Call `recall` before answering anything about a project's rules, decisions, architecture or
history. Pass the brain, which is the folder's own name lowercased; `brains` lists them.
Memory is markdown on disk: to write one, add a file under that folder's `memory/` and run
`/pmb digest`. Nothing here writes, on purpose."""


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
            name = item.get("document_name") or "?"
            text = item.get("text") or ""
            lines.append(f"--- {name}\n{text}")
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
            return "No brain has been digested yet. Run `/pmb digest` in a folder first."
        width = max(len(name) for name, _ in found)
        return "\n".join(f"{name:<{width}}  {count} document(s)" for name, count in found)

    return server


def main() -> None:
    # configure() before cognee is imported anywhere, because cognee reads its settings from
    # the environment at import time.
    config.configure()
    os.environ.setdefault("EMBEDDING_DIMENSIONS", "1024")
    build().run(
        transport="streamable-http",
        host=os.getenv("PMB_HOST", "0.0.0.0"),
        port=int(os.getenv("PMB_PORT", "8000")),
        streamable_http_path="/mcp",
    )


if __name__ == "__main__":
    main()
