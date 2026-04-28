---
description: Open the local Web UI to browse project / global claude-memory history
allowed-tools: Bash(claude-memory:*)
---

Start the local Web UI:

```bash
claude-memory web
```

This will:

- Start a FastAPI server on `127.0.0.1` on a free port
- Open the UI in the system default browser (use `claude-memory web --no-open` to skip)
- Let the user paginate, run keyword / semantic search, delete single turns, and tag turns
- Provide a scope toggle at the top of the page to switch between project and global history

Remind the user:

- Stop the server with `Ctrl+C`
- The server only listens on `127.0.0.1`; it is not exposed externally
- Default port is `9527`; override with `claude-memory web --port 8080`, or `--port 0` to let the OS pick a free port

UI delete and tag actions write to the database immediately:

- Delete: `DELETE /api/turns/{scope}/{id}` → removes the row from SQLite `turns` / `turn_tags` and clears the Chroma vector
- Tag: `POST /api/turns/{scope}/{id}/tags` → writes to `tags` / `turn_tags`
- Untag: `DELETE /api/turns/{scope}/{id}/tags/{name}` → clears `turn_tags`, then clears `tags` if no other turn uses it

Whatever the user does in the UI is the final state; no extra database commands are needed to sync.
