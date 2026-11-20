---
description: Set this machine up for PlugMyBrain - the stack, the agent wiring, and the /pmb commands
---

Set up PlugMyBrain on this machine. Run every step from the root of the plugmybrain checkout, which is the current working directory. It is safe to run again after pulling an update.

1. **Configuration.** Check that `.env` exists with `test -f .env`. **Never open, print or search it**: it holds keys. If it is missing, run `cp .env.example .env`, tell the user to fill it in, and stop until they say it is done. What they need to set:
   - The embedding: an API with its key, or Ollama with a local model.
   - `DB_PASSWORD`.
   - `PMB_WORKSPACE`, the absolute path of the folder holding every project to remember.
2. **Ollama.** Ask whether they chose Ollama. If so, run `ollama list`, and `ollama pull <model>` for the model they set if it is not there. If `ollama` is not installed, tell them to install it from ollama.com first.
3. **The stack.** Run `docker compose up -d --build`, then `docker compose ps` until `postgres` is healthy and `mcp` is up. If Docker is not running, ask the user to start Docker Desktop and try again. Never pass `-f compose.yaml`: compose then skips `compose.override.yaml` and recreates Postgres on a port the machine may already use.
4. **The agents.** Run `python -m plugmybrain.bootstrap`. It registers the server with Claude Code and Codex and installs the `/pmb-*` commands. It needs any Python 3.10 or later and no packages. Show its output.
5. **Next.** Tell the user to restart Claude Code and Codex, which load servers and commands at start, then run `/pmb-init brain` or `/pmb-init root` in each folder to remember, followed by `/pmb-digest`.
