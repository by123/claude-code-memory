"""MCP server exposing memory tools to Claude Code."""
from mcp.server.fastmcp import FastMCP

from .config import load_env
from .storage import Memory

load_env()

mcp = FastMCP("claude-memory")


@mcp.tool()
def search_memory(query: str, top_k: int = 5) -> dict:
    """Semantically search prior conversations and session summaries."""
    mem = Memory()
    try:
        results = mem.search(query, top_k=top_k, min_score=0.2)
        return {"count": len(results), "results": results}
    finally:
        mem.close()


@mcp.tool()
def list_recent(limit: int = 10) -> dict:
    """List the most recent raw conversation turns (newest first)."""
    mem = Memory()
    try:
        return {"turns": mem.list_recent(limit=limit)}
    finally:
        mem.close()


@mcp.tool()
def stats() -> dict:
    """Return counts across the memory stores."""
    mem = Memory()
    try:
        return mem.stats()
    finally:
        mem.close()


@mcp.tool()
def forget(id: str) -> dict:
    """Delete a turn or summary by id. Irreversible."""
    mem = Memory()
    try:
        ok = mem.forget(id)
        return {"deleted": ok, "id": id}
    finally:
        mem.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
