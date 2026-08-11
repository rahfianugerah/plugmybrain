---
description: Manage the PlugMyBrain memory - init, digest, reset or list
argument-hint: init root|brain [path] | digest | reset | list
---

Run PlugMyBrain for the user: $ARGUMENTS

**Do not use this command to answer questions.** The memory is connected as the `plugmybrain`
MCP server at {{MCP_URL}}, so a question is answered by calling its tools directly. This
command is only for the four actions below.

`PMB` below is this machine's checkout, already filled in:

```bash
PMB={{PMB_HOME}}
FOLDER=$(pwd)                       # or the path the user named
NAME=$(basename "$FOLDER" | tr '[:upper:]' '[:lower:]')
```

## init

Runs on the host, not in the container: it writes into the user's home directory, which the
container cannot see. Needs the `env` conda environment active.

```bash
pmb init root  "$FOLDER"       # a parent folder holding many projects, like maharum/
pmb init brain "$FOLDER"       # the rules and memory folder, like docs-standard/ or docs/
```

`root` and `brain` are the only two roles. A root is digested by walking its children; a brain
is scaffolded with `memory/` and `graph/` and is digested first, because everything else is
read against it. Both also register the MCP server with Claude Code and Codex and install this
command, so nothing is left to set up by hand.

## digest, reset, list

These run in the container. `pmb` on the host hangs on Cognee's subprocess workers on Windows,
and a killed run writes host paths into Postgres that no later run can resolve.

```bash
docker compose -f "$PMB/compose.yaml" run --rm \
  -v "$FOLDER:/w/$NAME" pmb <action> "/w/$NAME"
```

The mount path carries the folder's name on purpose: that name IS the memory it lands in, and a
fixed mount point would digest every folder into one shared memory that overwrites the last.

**digest** reads every markdown file into the memory, builds the code map, and writes the
knowledge graph back under `graph/` for Obsidian. On a root it does that for every child.

Run it with `--dry-run` first when the folder is large or new, show the user the estimate, and
wait for them to agree. It calls the model once per chunk and that is real money.

**reset** deletes that memory from the database and the generated `graph/code/` and `graph/kg/`.
`memory/` and every other markdown file are untouched, so a digest rebuilds everything. Add
`--all` for every folder. **Confirm with the user first**, then pass `--yes`, since the
container has no terminal to prompt on.

**list** shows what the database holds and how the folder's markdown count compares with what
was actually digested. Read-only, costs nothing, and is the right first step when something
looks stale.
