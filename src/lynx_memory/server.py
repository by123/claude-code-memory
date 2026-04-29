"""MCP server exposing memory tools to Claude Code and other MCP clients.

The server snapshots `os.getcwd()` at startup and uses it for `scope=auto`
resolution. Pass an explicit `scope` to override per-call.
"""
import os

from mcp.server.fastmcp import FastMCP

from .config import load_env, resolve_data_dir
from .storage import Memory, search_scoped

_STARTUP_CWD = os.getcwd()
load_env(resolve_data_dir(_STARTUP_CWD))

mcp = FastMCP("lynx-memory")


def _data_dir_for(scope: str):
    """Pick the single data dir for non-merged operations."""
    from .config import GLOBAL_DATA_DIR, find_project_root

    proj = find_project_root(_STARTUP_CWD)
    if scope == "auto":
        return proj or GLOBAL_DATA_DIR
    if scope == "project":
        return proj or GLOBAL_DATA_DIR  # graceful fallback
    return GLOBAL_DATA_DIR


@mcp.tool()
def search_memory(query: str, top_k: int = 5, scope: str = "auto") -> dict:
    """Semantically search prior conversations and session summaries.

    scope: auto | project | global | merged
    """
    results = search_scoped(
        query, cwd=_STARTUP_CWD, scope=scope, top_k=top_k, min_score=0.2
    )
    return {"count": len(results), "scope": scope, "results": results}


@mcp.tool()
def list_recent(limit: int = 10, scope: str = "auto") -> dict:
    """List the most recent raw conversation turns (newest first).

    scope: auto | project | global  (merged not supported here)
    """
    if scope == "merged":
        from .config import GLOBAL_DATA_DIR, find_project_root

        proj = find_project_root(_STARTUP_CWD)
        out = []
        if proj is not None:
            m = Memory(data_dir=proj)
            try:
                for r in m.list_recent(limit=limit):
                    r["scope"] = "project"
                    out.append(r)
            finally:
                m.close()
        g = Memory(data_dir=GLOBAL_DATA_DIR)
        try:
            for r in g.list_recent(limit=limit):
                r["scope"] = "global"
                out.append(r)
        finally:
            g.close()
        out.sort(key=lambda x: x.get("ts", 0), reverse=True)
        return {"turns": out[:limit], "scope": "merged"}

    mem = Memory(data_dir=_data_dir_for(scope))
    try:
        return {"turns": mem.list_recent(limit=limit), "scope": scope}
    finally:
        mem.close()


@mcp.tool()
def stats(scope: str = "auto") -> dict:
    """Return counts across the memory stores. scope: auto | project | global."""
    mem = Memory(data_dir=_data_dir_for(scope))
    try:
        out = mem.stats()
        out["scope"] = scope
        out["data_dir"] = str(mem.data_dir)
        return out
    finally:
        mem.close()


@mcp.tool()
def forget(id: str, scope: str = "auto") -> dict:
    """Delete a turn or summary by id. Irreversible. scope: auto | project | global."""
    mem = Memory(data_dir=_data_dir_for(scope))
    try:
        ok = mem.forget(id)
        return {"deleted": ok, "id": id, "scope": scope}
    finally:
        mem.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
