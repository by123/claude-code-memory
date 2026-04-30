# lynx-memory

[中文 README](./README.zh-CN.md)

Persistent, semantic, long-term memory for [Claude Code](https://claude.com/claude-code).
Conversations are auto-saved across sessions and the most relevant snippets are
injected into context whenever you start a new prompt — no special syntax,
no "remember this" phrasing required.

```
You      : What can I do tomorrow if the weather's nice — maybe walk the dog?
Claude   : Since you've got Dandan (your golden Border Collie) who needs a lot
           of exercise, try a long walk, frisbee, or a bike ride with him
           tagging along… 🐶
            (you never mentioned Dandan or owning a dog — memory recalled it
             from a past chat)
```

## How it works

Three Claude Code [hooks](https://docs.claude.com/en/docs/claude-code/hooks) +
a small Python service:

| Hook              | What it does                                                              |
| ----------------- | ------------------------------------------------------------------------- |
| `UserPromptSubmit` | Embeds your prompt and injects the top-K most similar prior turns. When a turn has a Haiku-generated summary, the **summary** is injected instead of the raw prose. |
| `Stop`             | Persists the current user/assistant turn into SQLite + Chroma, then spawns a detached background process that asks Haiku to summarize the turn (no extra API key needed — reuses your `claude` CLI session). |
| `SessionEnd`       | Asks Claude Haiku to produce a coarse summary of the whole session.       |

Storage:

- **SQLite** — source of truth for raw turns, per-turn Haiku summaries, and session summaries
- **Chroma** — local vector index over turns + summaries
- **Voyage AI** (`voyage-3`) — embeddings
- **Claude Haiku** (`claude-haiku-4-5-20251001`) — per-turn summarization, called via `claude -p` so no extra `ANTHROPIC_API_KEY` is required

## Install

```bash
pip install openlynx
lynx-memory init
```

`init` will:

1. Create `~/.claude/lynx-memory/` (data directory)
2. Prompt for your `VOYAGE_API_KEY` (get one free at https://www.voyageai.com/)
3. Write the default `.env` (`MIN_SCORE=0.7`, `SUMMARY_ENABLED=1`,
   `SUMMARY_MODEL=claude-haiku-4-5-20251001`, `SUMMARY_BACKEND=auto`) — the
   per-turn Haiku summarizer reuses your existing `claude` CLI session, so
   no extra `ANTHROPIC_API_KEY` is required by default
4. Back up your existing `~/.claude/settings.json` and add the three hooks
5. Print verification steps

Then open a fresh Claude Code session, chat for a few turns, and run:

```bash
lynx-memory status
```

You should see `turns` and `chroma_turns` counters going up.

## Codex CLI (cross-host memory)

Same memory store, also wired into [Codex CLI](https://developers.openai.com/codex/cli):

```bash
lynx-memory init --target codex   # or --target all to install both
```

This writes `~/.codex/hooks.json`, sets `[features] codex_hooks = true` in
`~/.codex/config.toml`, and registers three hooks (`UserPromptSubmit` →
inject, `Stop` → persist, `SessionStart` → summarize the previous session
since Codex has no `SessionEnd` event).

Codex's `additionalContext` field is fully respected, so retrieved memory
is injected exactly like in Claude Code. **Restart any running `codex`
process for hooks to take effect** — they're loaded at session start.

A turn typed in Claude Code can be recalled inside Codex (and vice versa)
because both write to the same SQLite + Chroma store at
`~/.claude/lynx-memory/`.

## CLI

```
lynx-memory init           Install hooks and slash commands
lynx-memory init-project   Create a .lynx-memory/ marker in cwd to enable
                             project-level storage
lynx-memory status         Show data dir, hook registration, DB stats
lynx-memory doctor         Verify Python, deps, API key, settings.json
lynx-memory merge          Merge memory between the project and global stores
                             (--from / --to is project|global, with --dry-run)
lynx-memory delete         Permanently delete memory for a scope
                             (--scope project|global|both, with double confirm)
lynx-memory uninstall      Remove hooks and slash commands (keeps your data)
```

## Slash commands

`lynx-memory init` also installs five global slash commands into
`~/.claude/commands/`, callable from any Claude Code session:

| Command                         | What it does                                                |
| ------------------------------- | ----------------------------------------------------------- |
| `/lynx-memory-status`         | Show current scope (project vs global) with stats for both  |
| `/lynx-memory-pull-global`    | Merge global memory into the current project (global → proj)|
| `/lynx-memory-push-global`    | Merge current project memory into global (proj → global)    |
| `/lynx-memory-delete`         | Delete memory with mandatory double confirm (`DELETE` + `y`)|
| `/lynx-memory-history`        | Open a local Web UI to browse, search, tag, and delete turns|

Each of these runs `lynx-memory status` / `merge --dry-run` first and asks
for your approval before any write or destructive action.

## Web UI

Type `/lynx-memory-history` in Claude Code (or run `lynx-memory web`) to
launch a local FastAPI + React UI on `127.0.0.1`. The page opens automatically
in your browser and lets you:

- Switch between **project** and **global** scopes
- Page through every saved turn
- Search by **keyword** (SQL `LIKE`) or **semantic** similarity (Voyage embeddings)
- Tag turns (e.g. `#work`, `#personal`) and filter by tag
- Delete a single turn (also clears its embedding from Chroma)
- See the per-turn **Haiku summary** above each turn, with a one-click button to (re)generate it on demand

### Usage

```bash
# default — listens on http://127.0.0.1:9527 and opens your browser
lynx-memory web

# pick a different port
lynx-memory web --port 8080

# or let the OS assign a free port
lynx-memory web --port 0

# don't auto-open the browser (useful in headless / SSH sessions)
lynx-memory web --no-open
```

| Action               | What happens on disk                                                        |
| -------------------- | --------------------------------------------------------------------------- |
| **Delete a turn**    | Row removed from SQLite `turns` and `turn_tags`; embedding removed from Chroma |
| **Add a tag**        | Inserted into SQLite `tags` (created on demand) and `turn_tags`             |
| **Remove a tag**     | Row removed from `turn_tags`; orphaned tag is GC'd from `tags`              |
| **Search (keyword)** | SQL `LIKE` over `user_msg` and `assistant_msg` — no embedding call          |
| **Search (semantic)**| One Voyage embedding per query, then top-K from Chroma                      |
| **Regenerate summary** | One `claude -p` call (Haiku); writes `summary` / `summary_model` / `summary_ts` back into the `turns` row |

The server only binds to `127.0.0.1`. Press `Ctrl+C` to stop it.

## Project-level vs global

Memory is global by default. Run this in a project root:

```bash
cd ~/code/my-project
lynx-memory init-project
```

It creates a `.lynx-memory/` marker. As long as your cwd is inside that
project, memory transparently switches to the project-level store at
`<project>/.lynx-memory/db/`, isolated from the global one at
`~/.claude/lynx-memory/`.

Use `/lynx-memory-status` to inspect the active scope, and
`/lynx-memory-pull-global` / `/lynx-memory-push-global` to move history
between the two layers.

## Configuration

All optional, set in `~/.claude/lynx-memory/.env`:

| Variable                       | Default                              | Purpose                                    |
| ------------------------------ | ------------------------------------ | ------------------------------------------ |
| `VOYAGE_API_KEY`               | —                                    | Required for embeddings                    |
| `TOP_K`                        | `5`                                  | Max memories injected per prompt           |
| `MIN_SCORE`                    | `0.7`                                | Cosine similarity floor (0–1)              |
| `SUMMARY_ENABLED`              | `1`                                  | Set `0`/`false` to disable per-turn Haiku summarization |
| `SUMMARY_MODEL`                | `claude-haiku-4-5-20251001`          | Model used for per-turn summaries          |
| `SUMMARY_BACKEND`              | `auto`                               | `auto` → CLI when `claude` is on PATH, else SDK; force with `cli` or `sdk` |
| `SUMMARY_TIMEOUT`              | `60`                                 | Seconds before the `claude -p` subprocess is killed |
| `ANTHROPIC_API_KEY`            | —                                    | Only needed when `SUMMARY_BACKEND=sdk` (CLI backend reuses your existing `claude` auth) |
| `LYNX_MEMORY_DIR`            | `~/.claude/lynx-memory`            | Where SQLite + Chroma live                 |
| `LYNX_MEMORY_SUMMARY_MODEL`  | `claude-haiku-4-5-20251001`          | Model used by `SessionEnd`                 |

## Optional: MCP server

You can also expose memory as MCP tools for Claude Code (`search_memory`,
`list_recent`, `stats`, `forget`). Add to `~/.claude.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "lynx-memory": {
      "command": "lynx-memory-mcp"
    }
  }
}
```

## Uninstall

```bash
lynx-memory uninstall                   # remove hooks + slash commands
lynx-memory delete --scope global       # delete the global store (confirms)
# or
rm -rf ~/.claude/lynx-memory            # nuke directly (irreversible)
```

## Privacy

- All data stays on your machine in `~/.claude/lynx-memory/`.
- Outbound calls: **Voyage AI** for embeddings (your prompt text), **Anthropic**
  for per-turn Haiku summaries (default; goes through your existing `claude`
  CLI session — no extra key) and end-of-session summaries.
- Set `SUMMARY_ENABLED=0` if you don't want per-turn summaries to leave the box.
- Set `LYNX_MEMORY_DIR` to encrypt at rest with whatever filesystem-level
  encryption your OS provides.

## Roadmap

- [x] **Project-level / global dual-layer storage**
  Global by default; auto-switches to project-level when a `.lynx-memory/`
  marker is found by walking up from cwd, so histories from different
  projects don't bleed into each other. Run `lynx-memory init-project`
  in a project root to create the marker. Search supports
  `scope=auto|project|global|merged` (hooks via `LYNX_MEMORY_SCOPE` env;
  MCP tools accept a `scope` argument).

- [x] **Codex CLI** — same hooks + shared store; use `lynx-memory init --target codex` (or `--target all`). See [Codex CLI](#codex-cli-cross-host-memory) above.

- [x] **Local Web UI memory browser**
  A local FastAPI + React UI with paging, keyword / semantic search,
  single-turn deletion, and tagging (e.g. `#work`, `#personal`). Launch with
  `/lynx-memory-history` (or `lynx-memory web`); the page exposes both
  project-level and global histories with a one-click scope toggle.

- [ ] **Other CLIs (Cursor, Gemini CLI, …)** — not integrated yet. **Cursor**: blocked until a stable hooks surface ships (we plan to adopt it once available); meanwhile MCP-only workflows remain possible where applicable.
- [ ] **Unified multi-client installer**
  A future `lynx-memory install --client <name>` to write MCP configs in one shot,
  with rules templates for consistent recall across clients that support them.

- [ ] **Import / export & cross-device sync**
  `lynx-memory export` / `import` for JSONL backup and restore; place `db/`
  in iCloud / Dropbox / a Git repo, or use a built-in `lynx-memory sync`
  subcommand to share memory across machines.

- [ ] **Richer automatic tagging (precise vs associative)**
  Stronger auto-labeling for turns, with a switchable **precise** mode
  (tight, literal, auditable tags) vs **associative** mode (broader links
  and softer clusters to improve semantic recall).

- [ ] **Recall modes & tunable ranking**
  Let users steer what gets injected beyond raw similarity — combine signals such as
  **retrieval / hit count**, **relevance score**, and **recency** (last used or last
  injected), with presets or manual weighting so priority matches your workflow.

## License

MIT — see [LICENSE](./LICENSE).
