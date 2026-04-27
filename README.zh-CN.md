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
| `UserPromptSubmit`  | 把你的 prompt 向量化，注入最相似的 K 条历史对话；命中的 turn 若已有 Haiku 摘要，注入的是**摘要**而不是原文 |
| `Stop`              | 把本轮 user/assistant 对话存入 SQLite + Chroma，并 **detached fork** 一个后台进程让 Haiku 生成本轮摘要（默认走 `claude -p`，无需额外 API Key） |
| `SessionEnd`        | 让 Claude Haiku 给整段会话生成一份粗粒度摘要          |

存储方式：

- **SQLite** — 原始对话、每轮 Haiku 摘要、会话级摘要的真实数据源
- **Chroma** — 本地向量索引（turns + 摘要）
- **Voyage AI** (`voyage-3`) — 文本向量化服务
- **Claude Haiku** (`claude-haiku-4-5-20251001`) — 每轮摘要，默认通过 `claude -p` 复用你已经登录的 Claude Code 鉴权

## 安装

```bash
pip install claude-code-memory
claude-memory init
```

`init` 会：

1. 创建数据目录 `~/.claude/claude-memory/`
2. 提示你输入 `VOYAGE_API_KEY`（免费申请：https://www.voyageai.com/）
3. 写入默认配置：`MIN_SCORE=0.7`、`SUMMARY_ENABLED=1`、
   `SUMMARY_MODEL=claude-haiku-4-5-20251001`、`SUMMARY_BACKEND=auto`
4. 备份现有的 `~/.claude/settings.json`，注入三个 hook
5. 打印验证步骤

然后开一个新的 Claude Code 会话，聊几轮后跑：

```bash
claude-memory status
```

你应该能看到 `turns` 和 `chroma_turns` 在涨。

## 命令

```
claude-memory init           安装 hooks 与 slash 命令
claude-memory init-project   在当前目录创建 .claude-memory/ 标记，启用项目级存储
claude-memory status         查看数据目录、hook 注册情况、数据库统计
claude-memory doctor         自检 Python、依赖、API key、settings.json
claude-memory merge          在项目级 / 全局两个仓库之间合并记忆
                             （--from / --to 选 project|global，可选 --dry-run）
claude-memory delete         永久删除某个 scope 的记忆
                             （--scope project|global|both，默认带二次确认）
claude-memory uninstall      卸载 hooks 与 slash 命令（保留数据）
```

## Slash 命令

`claude-memory init` 会顺带把以下五个全局 slash 命令安装到 `~/.claude/commands/`，
在任意 Claude Code 会话里直接调用：

| 命令                          | 作用                                                 |
| ----------------------------- | ---------------------------------------------------- |
| `/claude-memory-status`       | 查看当前是项目级还是全局，并显示两个仓库的统计       |
| `/claude-memory-pull-global`  | 把全局历史会话合并到当前项目（global → project）     |
| `/claude-memory-push-global`  | 把当前项目的历史会话合并到全局（project → global）   |
| `/claude-memory-delete`       | 永久删除记忆，对话里强制双重确认（输 `DELETE` + `y`）|
| `/claude-memory-history`      | 打开本地 Web UI 浏览历史，支持搜索、打标签、删除     |

这些命令是 Claude 自然语言执行模板，会自动跑 `claude-memory status` /
`merge --dry-run` 预览，并在合并 / 删除前征得你的同意。

## Web UI

在 Claude Code 里输 `/claude-memory-history`（或直接跑 `claude-memory web`），
会在 `127.0.0.1` 启动一个 FastAPI + React 的本地服务并自动开浏览器。在页面里你可以：

- 在 **项目级** 与 **全局** 之间一键切换
- 翻页浏览所有 turn
- **关键字**（SQL `LIKE`）或 **语义** 搜索（基于 Voyage 向量）
- 给单条 turn 打标签（如 `#work`、`#personal`），并按标签过滤
- 删除单条 turn（同时清掉 Chroma 里的向量）
- 每条 turn 顶部显示 **Haiku 摘要**，可一键"重新生成"

### 使用方式

```bash
# 默认 —— 监听 http://127.0.0.1:9527 并自动开浏览器
claude-memory web

# 换端口
claude-memory web --port 8080

# 让系统挑一个空闲端口
claude-memory web --port 0

# 不自动开浏览器（headless / SSH 场景）
claude-memory web --no-open
```

UI 上的操作直接落库：

| 操作         | 实际写入                                                              |
| ------------ | --------------------------------------------------------------------- |
| **删除 turn**| 同步删 SQLite 的 `turns` / `turn_tags` 行 + Chroma 向量               |
| **加标签**   | 写入 SQLite 的 `tags`（不存在则新建）和 `turn_tags`                   |
| **移除标签** | 删 `turn_tags`；如果该标签没人用了，再清 `tags` 里的孤立行            |
| **关键字搜索**| SQL `LIKE` 直查 `user_msg` / `assistant_msg`，不调用 embedding 接口 |
| **语义搜索** | 调一次 Voyage 算 query 向量，再从 Chroma 取 top-K                     |
| **重新生成摘要** | 调一次 `claude -p`（Haiku），把 `summary` / `summary_model` / `summary_ts` 写回 `turns`            |

服务只监听 `127.0.0.1`，按 `Ctrl+C` 关闭。

## 项目级 vs 全局

默认全局共享。在某个项目根目录跑：

```bash
cd ~/code/my-project
claude-memory init-project
```

会创建 `.claude-memory/` 标记目录。之后只要 cwd 在该项目内，记忆就自动切到
项目级仓库 `<project>/.claude-memory/db/`，与全局 `~/.claude/claude-memory/`
互不污染。

随时用 `/claude-memory-status` 查看当前 scope，用 `/claude-memory-pull-global`
/ `/claude-memory-push-global` 在两层之间搬运历史。

## 配置

全部可选，写在 `~/.claude/claude-memory/.env`：

| 变量                            | 默认值                              | 用途                              |
| ------------------------------- | ----------------------------------- | --------------------------------- |
| `VOYAGE_API_KEY`                | —                                   | 必填，向量化用                    |
| `TOP_K`                         | `5`                                 | 每次注入的最多记忆条数            |
| `MIN_SCORE`                     | `0.7`                               | 相似度下限（0–1）                 |
| `SUMMARY_ENABLED`               | `1`                                 | 设为 `0`/`false` 关闭每轮 Haiku 摘要 |
| `SUMMARY_MODEL`                 | `claude-haiku-4-5-20251001`         | 每轮摘要用的模型                  |
| `SUMMARY_BACKEND`               | `auto`                              | `auto`：PATH 上有 `claude` 时走 CLI，否则走 SDK；可强制 `cli` 或 `sdk` |
| `SUMMARY_TIMEOUT`               | `60`                                | `claude -p` 子进程超时秒数        |
| `ANTHROPIC_API_KEY`             | —                                   | 仅当 `SUMMARY_BACKEND=sdk` 时需要；CLI 后端复用 `claude` 自身鉴权 |
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
claude-memory uninstall                   # 移除 hooks 与 slash 命令
claude-memory delete --scope global       # 删除全局存储数据（带确认）
# 或
rm -rf ~/.claude/claude-memory            # 直接 rm（不可逆）
```

## 隐私说明

- 所有数据保存在你本机的 `~/.claude/claude-memory/`
- 外部请求：**Voyage AI**（embedding，包含你的 prompt 文本）；**Anthropic**
  Haiku 用于每轮摘要（默认走你已登录的 `claude` CLI，无需另配 key）和
  `SessionEnd` 会话级总结
- 不想让每轮内容被发去做摘要的话，设 `SUMMARY_ENABLED=0`
- 想加密静态数据的话，把 `CLAUDE_MEMORY_DIR` 指向一个加密卷即可

## Roadmap

- [x] **项目级 / 全局双层存储**
  默认全局共享，进入含 `.claude-memory/` 标记的项目目录后自动切换到项目级，避免不同项目的历史互相污染。在项目根目录运行 `claude-memory init-project` 创建标记。检索支持 `scope=auto|project|global|merged`（hooks 通过 `CLAUDE_MEMORY_SCOPE` 环境变量切换；MCP 工具直接传 `scope` 参数）。

- [ ] **多 CLI 客户端支持**
  在现有 Claude Code 基础上扩展到 **Cursor CLI、Codex CLI、Gemini CLI**，提供 `claude-memory install --client <name>` 一键写入 MCP 配置，并附带强制召回的 rules 模板，确保各客户端都能稳定触发记忆查询。

- [ ] **记忆导入 / 导出与跨设备同步**
  提供 `claude-memory export` / `import` 命令，支持 JSONL 格式备份与恢复；配合 iCloud / Dropbox / Git 仓库放置 `db/` 目录，或内置 `claude-memory sync` 子命令，实现多台设备记忆共享。

- [x] **本地 Web UI 记忆浏览器**
  基于 FastAPI + React 的本地可视化界面，支持翻页浏览、关键字 / 语义搜索、单条删除、打标签（如 `#work` `#personal`）等操作。通过 slash 命令 `/claude-memory-history`（或 `claude-memory web`）打开，页面同时展示项目级与全局的历史对话，可一键切换。

## 协议

MIT — 详见 [LICENSE](./LICENSE)。
