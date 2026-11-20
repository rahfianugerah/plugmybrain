---
description: Write what this session learned as one PlugMyBrain note, then digest it
argument-hint: [folder] [what to remember]
---

Write one PlugMyBrain memory note, then digest it so `recall` finds it: $ARGUMENTS

1. **Apply the test first, and be willing to fail it.** Would the next session waste time without this? Write only what is true beyond this session and not already in the code or the git history. If nothing passes, write nothing, digest nothing, and say so. One note per session, never one per turn.
2. **Pick the folder**: the one named above, or the current working directory. If it has no `memory/`, offer `/pmb-init brain` first.
3. **Pick the type**:

   | Type | Holds |
   | :- | :- |
   | `decision` | Why one option beat another, and what was rejected |
   | `session` | What happened, and what actually fixed it |
   | `fact` | Something durably true about the project or its environment |
   | `reference` | A pointer to something external |

4. **Write one file** with your own file tools: `<folder>/memory/<type>/<slug>.<type>.memory.md`, where the slug is the title in kebab-case. Use this shape, with today's date written out:

   ````markdown
   ---
   type: decision
   created: YYYY-MM-DD
   updated: YYYY-MM-DD
   tags: [project-name, topic]
   status: current
   ---

   # The title states the thing, not the topic

   > [!important]
   > The one line that changes what a reader does.

   The statement, in one or two sentences.

   **Why:** the reason it is true or was chosen.

   **Applies to:** where this matters.

   **Source:** the file that backs it, from the workspace root, or how to confirm it where no file does.

   ## Related

   - [[another-note.decision.memory.md]]
   ````

   - The callout carries the type: `[!important]` for a decision, `[!note]` for a session, `[!info]` for a fact, `[!quote]` for a reference.
   - A decision adds `**Decision:**` before `**Why:**`, and `**Rejected:**` and `**Cost accepted:**` after it.
   - "The loader uses Polars, not pandas" is a title. "Data loading notes" is not.
   - One paragraph per line, a `-` list for parallel items, and one screen at most.

5. **Never write** a secret, a key, a real configuration value, personal data about anyone else, a transcript, or a to-do. Never write into the database directly: it is an index, and a direct write is gone at the next digest.
6. **Digest the folder**: call the `plugmybrain` MCP server's `digest` tool with the folder's absolute path. While it says it is still running, call it again with the same folder. Then report the note's path and the digest result.
