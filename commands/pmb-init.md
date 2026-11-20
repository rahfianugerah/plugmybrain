---
description: Make a folder a PlugMyBrain root or brain, and scaffold its memory
argument-hint: root|brain [folder]
---

Initialise a folder for PlugMyBrain: $ARGUMENTS

The first word is the role. The folder is the path after it, or the current working directory. If no role was given, ask which one, and explain the two:

| Role | Is | Digested as |
| :- | :- | :- |
| `brain` | The rules and memory folder, such as a `docs/` | One memory named after the folder, digested before anything else |
| `root` | A parent folder holding many projects | Every child that has markdown, each its own memory, brains first |

A folder needs neither role to be digested. Roles exist so a parent can be digested in one call, and so a brain gets a `memory/` folder to write into.

Do the steps below with your own file tools. The server never writes into a project, on purpose.

1. Read `<folder>/.pmb` if it exists. If it names the other role, stop and tell the user: a role decides where the memory is built from, so they delete the file themselves if they mean to change it.
2. If `.pmb` is missing, write it holding the role and one newline.
3. For a brain only, create `memory/fact/`, `memory/decision/`, `memory/session/` and `memory/reference/`, each with an empty `.gitkeep`, and `memory/README.md` holding the text below. Never overwrite a file that already exists.
4. Call the `plugmybrain` MCP server's `brains` tool. If the tool is not available, the server is not connected: tell the user to start Docker Desktop, run `/pmb-setup` from the plugmybrain checkout, and restart this agent.
5. Report every file you created, and offer `/pmb-digest`.

The `memory/README.md` to write:

````markdown
# Memory

Human-authored. This folder is the memory; everything PlugMyBrain builds from it is an index that a digest rebuilds and a reset throws away.

| Folder | Answers | Example |
| :- | :- | :- |
| `fact/` | What is true | The conda environment for this project is `env` |
| `decision/` | Why it is this way | Chose Polars over pandas, because the file is 40GB |
| `session/` | What happened | Debugged the scaler leak, found it in `preprocess.py` |
| `reference/` | Where to look | The paper the architecture came from |

One note holds one thing, and its title states that thing. Write a note here with `/pmb-memory-digest`, or by hand followed by `/pmb-digest`.
````
