# claude-memory

[English README](./README.md)

为 [Claude Code](https://claude.com/claude-code) 提供持久、语义化的长期记忆。
对话会跨会话自动保存，每次你提交新消息时，最相关的历史片段会自动注入上下文——
不需要特殊语法，也不用说"还记得 XX 吗"。

```
你       : 明天天气好的话，我可以有哪些活动，比如遛狗
Claude   : 结合你有蛋蛋（金色边牧）这个大运动量的伙伴，可以安排长距离散步、
           玩飞盘、城市绿道骑行带它跟跑…… 🐶
            （你没提"蛋蛋"，也没说自己养狗——记忆从过往聊天里自动召回）
```

## 工作原理

三个 Claude Code [hooks](https://docs.claude.com/en/docs/claude-code/hooks) + 一个小 Python 服务：

| Hook                | 作用                                                  |
| ------------------- | ----------------------------------------------------- |
| `UserPromptSubmit`  | 把你的 prompt 向量化，注入最相似的 K 条历史对话       |
| `Stop`              | 把本轮 user/assistant 对话存入 SQLite + Chroma        |
| `SessionEnd`        | 让 Claude Haiku 给整段会话生成一份粗粒度摘要          |

存储方式：

- **SQLite** — 原始对话与摘要的真实数据源
- **Chroma** — 本地向量索引
- **Voyage AI** (`voyage-3`) — 文本向量化服务

## 安装

```bash
pip install claude-code-memory
claude-memory init
```

`init` 会：

1. 创建数据目录 `~/.claude/claude-memory/`
2. 提示你输入 `VOYAGE_API_KEY`（免费申请：https://www.voyageai.com/）
3. 备份现有的 `~/.claude/settings.json`，注入三个 hook
4. 打印验证步骤

然后开一个新的 Claude Code 会话，聊几轮后跑：

```bash
claude-memory status
```

你应该能看到 `turns` 和 `chroma_turns` 在涨。

## 命令

```
claude-memory init        安装 hooks
claude-memory status      查看数据目录、hook 注册情况、数据库统计
claude-memory doctor      自检 Python、依赖、API key、settings.json
claude-memory uninstall   卸载 hooks（保留数据）
```

## 配置

全部可选，写在 `~/.claude/claude-memory/.env`：

| 变量                            | 默认值                              | 用途                              |
| ------------------------------- | ----------------------------------- | --------------------------------- |
| `VOYAGE_API_KEY`                | —                                   | 必填，向量化用                    |
| `TOP_K`                         | `5`                                 | 每次注入的最多记忆条数            |
| `MIN_SCORE`                     | `0.3`                               | 相似度下限（0–1）                 |
| `CLAUDE_MEMORY_DIR`             | `~/.claude/claude-memory`           | SQLite + Chroma 数据目录          |
| `CLAUDE_MEMORY_SUMMARY_MODEL`   | `claude-haiku-4-5-20251001`         | `SessionEnd` 摘要用的模型         |

## 可选：MCP 服务

也可以把记忆暴露为 MCP 工具（`search_memory` / `list_recent` / `stats` / `forget`），
让 Claude 主动检索。在 `~/.claude.json` 或 `.mcp.json` 加：

```json
{
  "mcpServers": {
    "claude-memory": {
      "command": "claude-memory-mcp"
    }
  }
}
```

## 卸载

```bash
claude-memory uninstall            # 从 settings.json 移除 hooks
rm -rf ~/.claude/claude-memory     # 删除所有存储的数据（不可逆）
```

## 隐私说明

- 所有数据保存在你本机的 `~/.claude/claude-memory/`
- 唯一的外部请求是发给 **Voyage AI**（embedding，包含你的 prompt 文本）和
  **Anthropic**（生成会话摘要）
- 想加密静态数据的话，把 `CLAUDE_MEMORY_DIR` 指向一个加密卷即可

## Roadmap

- [ ] **项目级 / 全局双层存储**
  默认全局共享，进入项目目录后自动切换到项目级（通过 `.claude-memory/` 标记或配置项指定），避免不同项目的历史互相污染。检索时支持"仅本项目 / 仅全局 / 合并"三种模式。

- [ ] **多 CLI 客户端支持**
  在现有 Claude Code 基础上扩展到 **Cursor CLI、Codex CLI、Gemini CLI**，提供 `claude-memory install --client <name>` 一键写入 MCP 配置，并附带强制召回的 rules 模板，确保各客户端都能稳定触发记忆查询。

- [ ] **记忆导入 / 导出与跨设备同步**
  提供 `claude-memory export` / `import` 命令，支持 JSONL 格式备份与恢复；配合 iCloud / Dropbox / Git 仓库放置 `db/` 目录，或内置 `claude-memory sync` 子命令，实现多台设备记忆共享。

- [ ] **TUI 记忆浏览器**
  `claude-memory browse` 进入终端可视化界面，支持翻页浏览、关键字 / 语义搜索、单条删除、打标签（如 `#work` `#personal`）等操作。

## 协议

MIT — 详见 [LICENSE](./LICENSE)。
