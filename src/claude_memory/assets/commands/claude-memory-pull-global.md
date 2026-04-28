---
description: Merge global history into the current project (global → project)
allowed-tools: Bash(claude-memory:*)
---

You are helping the user merge the **global** claude-memory repo into the **current project** repo.

## Step 1: Check status before merging

```bash
claude-memory status
```

Report the current scope, whether the project and global repos exist, and the turn / summary counts of each.

## Step 2: Dry-run preview

```bash
claude-memory merge --from global --to project --dry-run
```

Tell the user how many entries will be copied and get confirmation before continuing.

## Step 3: Run the merge

```bash
claude-memory merge --from global --to project
```

**Do not pass `--delete-source` by default.** Only append `--delete-source` if the user explicitly asks to wipe the source repo, and confirm again — this is destructive.

## Step 4: Check status after merging

```bash
claude-memory status
```

Show the user the change in counts.

$ARGUMENTS
