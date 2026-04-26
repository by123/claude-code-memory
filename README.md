# claude-memory

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
| `UserPromptSubmit` | Embeds your prompt and injects the top-K most similar prior turns.        |
| `Stop`             | Persists the current user/assistant turn into SQLite + Chroma.            |
| `SessionEnd`       | Asks Claude Haiku to produce a coarse summary of the session.             |

Storage:

- **SQLite** — source of truth for raw turns and summaries
- **Chroma** — local vector index over both
- **Voyage AI** (`voyage-3`) — embeddings

## Install

```bash
pip install claude-code-memory
claude-memory init
```

`init` will:

1. Create `~/.claude/claude-memory/` (data directory)
2. Prompt for your `VOYAGE_API_KEY` (get one free at https://www.voyageai.com/)
3. Back up your existing `~/.claude/settings.json` and add the three hooks
4. Print verification steps

Then open a fresh Claude Code session, chat for a few turns, and run:

```bash
claude-memory status
```

You should see `turns` and `chroma_turns` counters going up.

## CLI

```
claude-memory init           Install hooks and slash commands
claude-memory init-project   Create a .claude-memory/ marker in cwd to enable
                             project-level storage
claude-memory status         Show data dir, hook registration, DB stats
claude-memory doctor         Verify Python, deps, API key, settings.json
claude-memory merge          Merge memory between the project and global stores
                             (--from / --to is project|global, with --dry-run)
claude-memory delete         Permanently delete memory for a scope
                             (--scope project|global|both, with double confirm)
claude-memory uninstall      Remove hooks and slash commands (keeps your data)
```

## Slash commands

`claude-memory init` also installs five global slash commands into
`~/.claude/commands/`, callable from any Claude Code session:

| Command                         | What it does                                                |
| ------------------------------- | ----------------------------------------------------------- |
| `/claude-memory-status`         | Show current scope (project vs global) with stats for both  |
| `/claude-memory-pull-global`    | Merge global memory into the current project (global → proj)|
| `/claude-memory-push-global`    | Merge current project memory into global (proj → global)    |
| `/claude-memory-delete`         | Delete memory with mandatory double confirm (`DELETE` + `y`)|
| `/claude-memory-history`        | Open a local Web UI to browse, search, tag, and delete turns|

Each of these runs `claude-memory status` / `merge --dry-run` first and asks
for your approval before any write or destructive action.

## Web UI

Type `/claude-memory-history` in Claude Code (or run `claude-memory web`) to
launch a local FastAPI + React UI on `127.0.0.1`. The page opens automatically
in your browser and lets you:

- Switch between **project** and **global** scopes
- Page through every saved turn
- Search by **keyword** (SQL `LIKE`) or **semantic** similarity (Voyage embeddings)
- Tag turns (e.g. `#work`, `#personal`) and filter by tag
- Delete a single turn (also clears its embedding from Chroma)

### Usage

```bash
# default — listens on http://127.0.0.1:9527 and opens your browser
claude-memory web

# pick a different port
claude-memory web --port 8080

# or let the OS assign a free port
claude-memory web --port 0

# don't auto-open the browser (useful in headless / SSH sessions)
claude-memory web --no-open
```

| Action               | What happens on disk                                                        |
| -------------------- | --------------------------------------------------------------------------- |
| **Delete a turn**    | Row removed from SQLite `turns` and `turn_tags`; embedding removed from Chroma |
| **Add a tag**        | Inserted into SQLite `tags` (created on demand) and `turn_tags`             |
| **Remove a tag**     | Row removed from `turn_tags`; orphaned tag is GC'd from `tags`              |
| **Search (keyword)** | SQL `LIKE` over `user_msg` and `assistant_msg` — no embedding call          |
| **Search (semantic)**| One Voyage embedding per query, then top-K from Chroma                      |

The server only binds to `127.0.0.1`. Press `Ctrl+C` to stop it.

## Project-level vs global

Memory is global by default. Run this in a project root:

```bash
cd ~/code/my-project
claude-memory init-project
```

It creates a `.claude-memory/` marker. As long as your cwd is inside that
project, memory transparently switches to the project-level store at
`<project>/.claude-memory/db/`, isolated from the global one at
`~/.claude/claude-memory/`.

Use `/claude-memory-status` to inspect the active scope, and
`/claude-memory-pull-global` / `/claude-memory-push-global` to move history
between the two layers.

## Configuration

All optional, set in `~/.claude/claude-memory/.env`:

| Variable                       | Default                              | Purpose                                    |
| ------------------------------ | ------------------------------------ | ------------------------------------------ |
| `VOYAGE_API_KEY`               | —                                    | Required for embeddings                    |
| `TOP_K`                        | `5`                                  | Max memories injected per prompt           |
| `MIN_SCORE`                    | `0.3`                                | Cosine similarity floor (0–1)              |
| `CLAUDE_MEMORY_DIR`            | `~/.claude/claude-memory`            | Where SQLite + Chroma live                 |
| `CLAUDE_MEMORY_SUMMARY_MODEL`  | `claude-haiku-4-5-20251001`          | Model used by `SessionEnd`                 |

## Optional: MCP server

You can also expose memory as MCP tools for Claude Code (`search_memory`,
`list_recent`, `stats`, `forget`). Add to `~/.claude.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "claude-memory": {
      "command": "claude-memory-mcp"
    }
  }
}
```

## Uninstall

```bash
claude-memory uninstall                   # remove hooks + slash commands
claude-memory delete --scope global       # delete the global store (confirms)
# or
rm -rf ~/.claude/claude-memory            # nuke directly (irreversible)
```

## Privacy

- All data stays on your machine in `~/.claude/claude-memory/`.
- The only outbound call is to **Voyage AI** for embeddings (your prompt text)
  and **Anthropic** for end-of-session summaries.
- Set `CLAUDE_MEMORY_DIR` to encrypt at rest with whatever filesystem-level
  encryption your OS provides.

## Roadmap

- [x] **Project-level / global dual-layer storage**
  Global by default; auto-switches to project-level when a `.claude-memory/`
  marker is found by walking up from cwd, so histories from different
  projects don't bleed into each other. Run `claude-memory init-project`
  in a project root to create the marker. Search supports
  `scope=auto|project|global|merged` (hooks via `CLAUDE_MEMORY_SCOPE` env;
  MCP tools accept a `scope` argument).

- [ ] **Multi-CLI client support**
  Extend beyond Claude Code to **Cursor CLI, Codex CLI, Gemini CLI**. Provide
  `claude-memory install --client <name>` to write MCP configs in one shot,
  with rules templates that force consistent recall on each client.

- [ ] **Import / export & cross-device sync**
  `claude-memory export` / `import` for JSONL backup and restore; place `db/`
  in iCloud / Dropbox / a Git repo, or use a built-in `claude-memory sync`
  subcommand to share memory across machines.

- [x] **Local Web UI memory browser**
  A local FastAPI + React UI with paging, keyword / semantic search,
  single-turn deletion, and tagging (e.g. `#work`, `#personal`). Launch with
  `/claude-memory-history` (or `claude-memory web`); the page exposes both
  project-level and global histories with a one-click scope toggle.

## License

MIT — see [LICENSE](./LICENSE).
