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
claude-memory init        Install hooks
claude-memory status      Show data dir, hook registration, DB stats
claude-memory doctor      Verify Python, deps, API key, settings.json
claude-memory uninstall   Remove hooks (keeps your data)
```

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
claude-memory uninstall            # removes hooks from settings.json
rm -rf ~/.claude/claude-memory     # delete all your stored data (irreversible)
```

## Privacy

- All data stays on your machine in `~/.claude/claude-memory/`.
- The only outbound call is to **Voyage AI** for embeddings (your prompt text)
  and **Anthropic** for end-of-session summaries.
- Set `CLAUDE_MEMORY_DIR` to encrypt at rest with whatever filesystem-level
  encryption your OS provides.

## Roadmap

- [ ] **Project-level / global dual-layer storage**
  Global by default; auto-switch to project-level when a `.claude-memory/`
  marker (or config) is present in the working directory, so histories from
  different projects don't bleed into each other. Search supports
  "project only / global only / merged" modes.

- [ ] **Multi-CLI client support**
  Extend beyond Claude Code to **Cursor CLI, Codex CLI, Gemini CLI**. Provide
  `claude-memory install --client <name>` to write MCP configs in one shot,
  with rules templates that force consistent recall on each client.

- [ ] **Import / export & cross-device sync**
  `claude-memory export` / `import` for JSONL backup and restore; place `db/`
  in iCloud / Dropbox / a Git repo, or use a built-in `claude-memory sync`
  subcommand to share memory across machines.

- [ ] **TUI memory browser**
  `claude-memory browse` opens a terminal UI with paging, keyword / semantic
  search, single-entry deletion, and tagging (e.g. `#work`, `#personal`).

## License

MIT — see [LICENSE](./LICENSE).
