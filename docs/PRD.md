# PRD: PlugMyBrain

| Field | Value |
| :- | :- |
| Owner | rahfianugerah |
| Date | 20 November 2026 |
| Status | <code style="color: yellow">Draft</code> |
| Goal | Every coding agent on a machine answers from a shared, sourced memory of the projects it works on, reached entirely through MCP and slash commands, with nothing to pay per question |

## Problem

A coding agent starts every session with no memory of the project. It rereads the same rules, decisions and history each time, pays for that in tokens, and still answers from general knowledge when it reads the wrong file. A memory kept inside one vendor's product does not help either: it is gone the day the model changes.

The earlier version of PlugMyBrain solved the memory but not the friction. Every digest, status check and reset was a `docker compose run` typed by hand, with a different form for Git Bash and PowerShell and a mount path that had to repeat the folder name exactly. A chat-model extraction step also made one digest of a 3.6MB corpus cost about $9.

## Users

- The owner, daily: one developer working across personal and work repositories with Claude Code and Codex on Windows, with the standards and decisions for each kept as markdown in an Obsidian vault.
- Any developer who clones the public repository to give their own agents a memory. They are assumed to run Docker and an MCP-capable agent, and to keep their knowledge in markdown.

## What Is Built

- Make any folder of markdown a memory named after the folder, from the agent, with `/pmb-digest`.
- Give a parent folder the `root` role so one digest makes every child project its own memory, the rules folder first.
- Answer a question from one memory or several, with the source file for every passage, through `recall` or `/pmb-recall`.
- Ask where something lives in a codebase through a code map Graphify extracts locally, through `code_map` or `/pmb-code`.
- Write what a session learned as one reviewed markdown note in the folder's `memory/`, and digest it or not, with `/pmb-memory-digest` and `/pmb-memory-no-digest`.
- See what a folder holds against what was digested, the embedding model, and the running job, with `/pmb-status`.
- Switch which memory a session reads with `/pmb-map`, and delete a memory with a confirmed `/pmb-reset`.
- Embed with an API, Voyage by default, or with a local Ollama model and no key.
- Set the machine up once with `/pmb-setup`, after which no terminal command is needed.
- Keep Postgres on an always-on VM when the database should outlive the laptop.

## What Is Not Built

- **A chat model, or a written answer.** The agent asking already has a model. A second one would add a bill and a place for answers to drift from their sources.
- **An entity graph across documents.** It needs a chat model to extract entities, which is the cost removed on purpose.
- **Formats other than markdown.** PDF, docx and csv are converted by the user first. Obsidian is the viewer and markdown is the substrate.
- **Writing into a project from the server.** The workspace is mounted read-only. Notes are written by the agent's own file tools, where the user sees and reviews them.
- **Writing into the index directly.** A note that exists only in the database is lost at the next rebuild.
- **Accounts, authentication or multiple tenants.** It is one person's memory behind loopback.
- **A hosted service.** It runs on the user's machine, or on the user's own VM.
- **Questions about the past state of the memory.** Git history answers those.

## Success Measure

- From a fresh clone to a first sourced `recall` answer using only the setup step and slash commands, with no `docker` command typed by the user after `/pmb-setup`.
- A `recall` against one brain never returns a passage from another, including when both hold a file with the same name.
- A digest with Ollama sends nothing off the machine and costs nothing.
- A second digest of an unchanged folder embeds nothing new.
- Every digest, status and reset completes or reports progress within one tool call of 45 seconds, under Codex's default timeout.

## Constraints

- One PostgreSQL 18 database with pgvector holds the relational, vector and graph stores.
- Embeddings are at most 2000 dimensions, the widest pgvector indexes; 1024 by default.
- The stack fits a 2 GiB machine: the server is capped at 1500 MB and runs one job at a time.
- The server reads only the folder in `PMB_WORKSPACE`, read-only.
- Ingestion runs in the Linux container: on the Windows host Cognee's subprocess workers hang.
- Cognee is pinned at 1.4.2 and Graphify at 0.9.38; both are internal APIs this project depends on.
- Every port binds to loopback.

## Data

- **Read:** every markdown file under a digested folder, except paths matching the secret exclusion list (`.env`, keys, credential files, `keys/`, `.git`, `node_modules`). Source files are read by Graphify, locally.
- **Written:** chunk text, vectors and document links in Postgres; the code map report in the vault's `graph/code/`; `graph.json` in the checkout. Nothing is written into a digested folder.
- **Leaves the machine:** with an embedding API, every chunk's text goes to that provider. With Ollama, nothing does.
- **Personal data:** whatever the user's markdown holds. The project collects none of its own, and the name-based exclusion list does not catch a secret pasted into an ordinary note.

## Open Questions

- **The license.** Decided by the owner.
- **Distribution as a Claude Code plugin**, which would install the commands and register the server in one step without the Python wiring. Decided by the owner.
- **A local chat model for an entity graph**, through Ollama, now that a model can run without a bill. Decided by the owner, against the extra memory a 2 GiB machine does not have.
