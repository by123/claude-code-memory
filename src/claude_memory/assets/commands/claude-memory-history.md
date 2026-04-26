---
description: 打开本地 Web UI 浏览 claude-memory 的项目级 / 全局历史对话
allowed-tools: Bash(claude-memory:*)
---

请用中文回答。

启动本地 Web UI：

```bash
claude-memory web
```

执行后会做这几件事：

- 在 `127.0.0.1` 上选一个空闲端口启动 FastAPI 服务
- 自动用系统默认浏览器打开 UI（如果不希望自动开，可改用 `claude-memory web --no-open`）
- 用户可以在浏览器里翻页浏览、关键字 / 语义搜索、单条删除、给 turn 打标签
- 项目级和全局历史可在页面顶部切换

提醒用户：

- 关闭服务用 `Ctrl+C`
- 服务只监听 `127.0.0.1`，不对外开放
- 默认端口 `9527`；想换端口：`claude-memory web --port 8080`，或用 `--port 0` 让系统分配空闲端口

UI 上的删除和打标签操作会真实写库：

- 删除：`DELETE /api/turns/{scope}/{id}` → 同时清掉 SQLite 的 `turns` / `turn_tags` 行 + Chroma 向量
- 打标签：`POST /api/turns/{scope}/{id}/tags` → 写入 `tags` / `turn_tags`
- 取消标签：`DELETE /api/turns/{scope}/{id}/tags/{name}` → 清 `turn_tags`，若该标签没人用了再清 `tags`

用户在 UI 上点的操作即为最终态；不需要再额外执行数据库命令去同步。
