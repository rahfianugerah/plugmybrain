# Contributing to PlugMyBrain

PlugMyBrain is maintained by one person and open to contributions from anyone who uses it. Every contribution follows the conventions below, so the history stays readable and the memory it builds stays trustworthy.

## Table of Contents

1. [Before You Start](#before-you-start)
2. [Setting Up](#setting-up)
3. [Branches](#branches)
4. [Commits](#commits)
5. [Pull Requests](#pull-requests)
6. [Code Style and Tests](#code-style-and-tests)
7. [Reporting a Bug or Requesting a Feature](#reporting-a-bug-or-requesting-a-feature)
8. [Reporting a Security Issue](#reporting-a-security-issue)

## Before You Start

- Read the [README](README.md) for what the project is and how it runs, and [docs/PRD.md](docs/PRD.md) for what it deliberately does not do.
- Read the [Code of Conduct](CODE_OF_CONDUCT.md). It applies to every contribution.
- Check the open issues and pull requests, so two people do not build the same thing.
- **A new MCP tool or slash command needs a reason in the issue first.** Every tool an agent can see costs context on every turn, so the surface stays small on purpose.

## Setting Up

1. Clone the repository:

   ```bash
   git clone https://github.com/rahfianugerah/plugmybrain.git
   cd plugmybrain
   ```

2. Create the environment:

   ```bash
   conda env update -f environment.yml
   conda activate env
   pip install -e .
   ```

3. Copy `.env.example` to `.env` and fill in the values. **Never commit `.env`.**
4. Run the tests to confirm the setup:

   ```bash
   pytest
   ```

5. To run the real stack, `docker compose up -d --build`, then `python -m plugmybrain.bootstrap` to point your agents at it.

## Branches

- Promotion: branch from `dev`; changes move `dev` to `staging` to `main`, each by pull request. Never commit straight to `staging` or `main`, and never merge backwards.
- A hotfix is the one exception: it branches from `main`, merges to `main`, and is carried back to `dev` and `staging` the same day.
- Name a branch `<type>/<description>` in lowercase kebab-case, such as `feat/csv-export` or `fix/session-timeout`. No emoji and no personal names.

## Commits

Every commit follows Conventional Commits, in English:

```text
<type>(<scope>): <description>

- One list item per change, saying what it does and why
```

- The type is one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, or `revert`.
- The description is imperative, lowercase, without a trailing period, and about 72 characters.
- One concern per commit.
- No emoji.
- Never commit a secret, a key, an `.env` file, or real data.

## Pull Requests

- One concern per pull request.
- The description carries a **Summary**, a **Changes** list, and a **Test Plan** whose items are ticked with `- [x]` only for steps actually run.
- Every check passes, and the branch is up to date with its base, before review.
- The maintainer reviews and merges every pull request.

## Code Style and Tests

- `ruff check .` and `ruff format .`, both clean.
- A public function carries type hints.
- A comment is a short label, one line by default and three at most.
- A bug fix ships with the test that would have caught it.
- A change to a command in `commands/` is tested by running it in Claude Code or Codex after `python -m plugmybrain.bootstrap`.

## Reporting a Bug or Requesting a Feature

Open an issue with what you did, what you expected, and what happened, quoting any error verbatim, and the version or commit you used. For a digest problem, include the output of `/pmb-status`.

## Reporting a Security Issue

Never in a public issue. Follow [SECURITY.md](SECURITY.md).
