---
description: Show the current claude-memory scope (project / global) and stats
allowed-tools: Bash(claude-memory:*)
---

Run:

```bash
claude-memory status
```

Summarize the key points for the user:

- **Current scope**: `project` or `global`
- Path of the **active data directory**
- Number of sessions / turns / summaries
- Whether a project-level repo `./.claude-memory/` exists in the current directory
- Whether the global repo `~/.claude/claude-memory/` exists

Do not perform any write or merge operations.
