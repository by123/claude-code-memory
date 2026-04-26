---
description: 把全局历史会话合并到当前项目（global → project）
allowed-tools: Bash(claude-memory:*)
---

请用中文回答。你正在帮用户把 **全局** claude-memory 仓库合并进 **当前项目** 仓库。

## 步骤 1：合并前先看状态

```bash
claude-memory status
```

向用户报告当前 scope、项目仓库与全局仓库是否存在、各自的 turn / summary 数量。

## 步骤 2：dry-run 预览

```bash
claude-memory merge --from global --to project --dry-run
```

把将会复制的条数告诉用户，征得同意后再继续。

## 步骤 3：执行合并

```bash
claude-memory merge --from global --to project
```

**默认不要带 `--delete-source`**。只有用户明确说要清空源仓库时，才追加 `--delete-source` 并再次确认（破坏性操作）。

## 步骤 4：合并后再看一次状态

```bash
claude-memory status
```

把数量变化展示给用户。

$ARGUMENTS
