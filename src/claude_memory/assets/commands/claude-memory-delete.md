---
description: 永久删除 claude-memory 的历史数据（需要二次确认）
allowed-tools: Bash(claude-memory:*)
---

请用中文回答。你正在帮用户 **永久删除** claude-memory 的历史数据（sqlite + chroma 向量库）。这是不可逆操作，必须严格按下面流程走。

## 步骤 1：先看当前状态

```bash
claude-memory status
```

向用户报告：项目仓库 `./.claude-memory/` 与全局仓库 `~/.claude/claude-memory/` 是否存在、各自的 turn / summary 数量。

## 步骤 2：询问要删除哪个 scope

明确给用户三个选项，并要求他选一个：

- `project` — 仅删除当前项目的记忆
- `global` — 仅删除全局记忆
- `both` — 两个一起删

## 步骤 3：第一次确认

复述将要删除的目录路径与条数，问用户：「确认删除吗？请回复 `DELETE` 继续。」

- 用户必须**完整回复 `DELETE` 这个英文单词**才算通过第一次确认。
- 任何其他回答都视为放弃，立即停止并告知用户已取消。

## 步骤 4：第二次确认

第一次通过后，再问一次：「最后一次确认：你确定要永久删除 [scope] 的全部记忆吗？(y/N)」

- 用户必须明确回复 `y` 或 `yes`。
- 任何其他回答都视为放弃，立即停止并告知用户已取消。

## 步骤 5：执行删除

只有在两次确认都通过后才执行：

```bash
claude-memory delete --scope <project|global|both> --yes
```

（`--yes` 是因为你已经在对话里完成了双重确认；CLI 自身的交互确认可以跳过。）

## 步骤 6：删除后再看一次状态

```bash
claude-memory status
```

把变化报给用户。

$ARGUMENTS
