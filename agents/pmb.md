---
description: Manage the PlugMyBrain memory for this folder - digest, reset, or list
argument-hint: digest | reset | list
---

Run PlugMyBrain against the folder the user is working in: $ARGUMENTS

**Do not use this command to answer questions.** The memory is already connected as the
`plugmybrain` MCP server, so a question is answered by calling its tools directly. This command
is only for the three management actions below.

Everything runs in the container. `pmb` on the host hangs on Cognee's subprocess workers on
Windows, and a killed run writes host paths into Postgres that no later run can resolve.

Set `PMB_HOME` to the PlugMyBrain checkout once, then:

```bash
FOLDER=$(pwd)                       # or the path the user named
NAME=$(basename "$FOLDER" | tr '[:upper:]' '[:lower:]')
docker compose -f "$PMB_HOME/compose.yaml" run --rm \
  -v "$FOLDER:/w/$NAME" pmb <action> "/w/$NAME"
```

The mount path carries the folder's name on purpose: that name IS the memory it lands in, and a
fixed mount point would digest every folder into one shared memory that overwrites the last.

## digest

Reads every markdown file in the folder into the memory, builds the code map, and writes the
knowledge graph back as markdown under `graph/`, which Obsidian renders.

Run `... pmb digest "/w/$NAME" --dry-run` first when the folder is large or has not been
digested before, show the user the estimate, and wait for them to agree. It calls the model
once per chunk and that is real money.

## reset

Deletes this folder's memory from the database and its generated `graph/`. `memory/` and every
other markdown file are untouched, so a digest rebuilds everything.

Add `--all` to wipe every folder's memory, not just this one. **Confirm with the user before
running either.** Pass `--yes` only after they have said yes, since the container has no
terminal to prompt on.

## list

Shows what the database holds, every memory in it, and how the folder's markdown count compares
with what was actually digested. Read-only, costs nothing, and is the right first step when
something looks stale.
