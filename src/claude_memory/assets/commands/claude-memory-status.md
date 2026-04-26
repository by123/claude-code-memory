---
description: 查看 claude-memory 当前作用域（项目级 / 全局）与统计信息
allowed-tools: Bash(claude-memory:*)
---

请用中文回答。

执行：

```bash
claude-memory status
```

把要点总结给用户：

- **当前 scope**：是 `project` 还是 `global`
- **active 数据目录**的路径
- 会话 / turn / summary 的数量
- 当前目录是否存在项目级仓库 `./.claude-memory/`
- 全局仓库 `~/.claude/claude-memory/` 是否存在

不要执行任何写入或合并操作。
