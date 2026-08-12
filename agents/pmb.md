---
description: Manage the PlugMyBrain memory - init, digest, memory, reset or list
argument-hint: init root|brain [path] | digest | memory | reset | list
---

Run PlugMyBrain for the user: $ARGUMENTS

**Do not use this command to answer questions.** The memory is connected as the `plugmybrain`
MCP server at {{MCP_URL}}, so a question is answered by calling its tools directly. This
command is only for the actions below.

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
cd "$PMB" && MSYS_NO_PATHCONV=1 docker compose run --rm \
  -v "$FOLDER:/w/$NAME" pmb <action> "/w/$NAME"
```

**`cd`, never `-f "$PMB/compose.yaml"`.** Compose only picks `compose.override.yaml` up when it
finds the file itself, so naming one with `-f` drops the override, and Postgres is then
recreated on the default port a development machine usually already owns. That takes the
running stack down before the action even starts.

**`MSYS_NO_PATHCONV=1` is what makes it work in Git Bash**, which rewrites `/w/<name>` into
`W:/<name>` and fails with `not a directory: /app/W:/...`. It is an unused variable everywhere
else, so the one command is correct on every shell and every platform.

The mount path carries the folder's name on purpose: that name IS the memory it lands in, and a
fixed mount point would digest every folder into one shared memory that overwrites the last.

**digest** chunks and embeds every markdown file, and builds the Graphify code map into the
vault. On a root it does that for every child, brain first. There is no chat model involved and
nothing to estimate: the only cost is Voyage embedding, which is free at this scale.

**reset** deletes that memory from the database and its `graph/code/<brain>/` in the vault.
`memory/` and every other markdown file are untouched, so a digest rebuilds everything. Add
`--all` for every folder. **Confirm with the user first**, then pass `--yes`, since the
container has no terminal to prompt on.

**list** shows what the database holds and how the folder's markdown count compares with what
was actually digested. Read-only, costs nothing, and is the right first step when something
looks stale.

## memory

Write what this session learned into the folder's `memory/`, then digest it.

**No `pmb` subcommand does this, and none should.** The note is a markdown file, and you write
it with the tools you already have. That is why the CLI is still four commands: a command here
would add a step that writes nothing you could not write yourself.

**First apply the test from the vault's `memory.rules.md`, and be willing to fail it:** would
the next session waste time without this? If not, write nothing and say so. A memory full of
noise is a memory nobody reads. One note per session, never one per turn.

If it passes, write ONE file to `$FOLDER/memory/<type>/<kebab-slug-of-the-title>.md`:

| Type | Holds |
| :- | :- |
| `decision` | Why one option beat another, and what was rejected |
| `session` | What happened, and what actually fixed it |
| `fact` | Something durably true about the project or its environment |
| `reference` | A pointer to something external |

Use the frontmatter from the vault's `note.template.md`: `type`, `created`, `updated`, `tags`
and `status`, with absolute dates rather than "yesterday". The title states the thing, not the
topic: "The loader uses Polars, not pandas" beats "Data loading notes". Write the `**Why:**`
line, because the conclusion without the reason is dropped the first time it is inconvenient.
Link related notes with `[[wikilinks]]`, which is what connects them in Obsidian's graph, and
keep the whole note to one screen.

Never write the transcript, a secret, a real configuration value, or anything the code and git
history already say. **Never write into Cognee directly:** it is an index, and a direct write is
gone at the next rebuild with nothing to warn you.

Then run the `digest` command above on the same folder, so `recall` can find it.
