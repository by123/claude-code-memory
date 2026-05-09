"""Local Web UI for browsing lynx-memory.

Run with `lynx-memory web`.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import GLOBAL_DATA_DIR, find_project_root, load_env
from .storage import Memory, get_shared_memory, memory_lock

logger = logging.getLogger("lynx_memory.web")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
logger.setLevel(logging.INFO)


def _scope_dir(scope: str) -> Optional[Path]:
    if scope == "global":
        return GLOBAL_DATA_DIR
    if scope == "project":
        return find_project_root(Path.cwd())
    raise HTTPException(status_code=400, detail=f"unknown scope: {scope!r}")


def _sqlite_turn_count(data_dir: Path) -> int:
    """Count turns without opening Chroma (avoids concurrent PersistentClient init)."""
    db_path = data_dir / "db" / "memory.db"
    if not db_path.is_file():
        return 0
    try:
        con = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            row = con.execute("SELECT COUNT(*) FROM turns").fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()
    except Exception:
        return 0


@contextmanager
def _memory_for(scope: str) -> Iterator[Memory]:
    """Yield a process-shared Memory for `scope`, serialized per data_dir.

    The instance is cached process-wide (chromadb init is expensive and
    racy if re-entered concurrently); the per-store RLock ensures we don't
    interleave multi-statement work across requests.
    """
    d = _scope_dir(scope)
    if d is None:
        raise HTTPException(status_code=404, detail=f"scope {scope!r} not available")
    with memory_lock(d):
        yield get_shared_memory(d)


def _static_dir() -> Optional[Path]:
    try:
        ref = resources.files("lynx_memory.assets") / "web"
    except Exception:
        return None
    p = Path(str(ref))
    return p if p.is_dir() and (p / "index.html").exists() else None


class TagBody(BaseModel):
    name: str
    kind: str = "custom"


class OpenFileBody(BaseModel):
    path: str
    line: Optional[int] = None


def _try_open_with_command(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _attach_retrieval_counts(mem: Memory, items: list) -> None:
    if not items:
        return
    counts = mem.hit_counts_for_turns([t["id"] for t in items])
    for t in items:
        t["retrieval_count"] = counts.get(t["id"], 0)


def create_app() -> FastAPI:
    load_env()
    app = FastAPI(title="lynx-memory web")
    logger.info("web app init cwd=%s", Path.cwd())

    @app.middleware("http")
    async def log_api_requests(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        started = time.perf_counter()
        logger.info("api request %s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "api error %s %s (%.1fms)",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "api response %s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.get("/api/scopes")
    def get_scopes() -> dict:
        proj = find_project_root(Path.cwd())
        g_count = _sqlite_turn_count(GLOBAL_DATA_DIR)
        p_count = _sqlite_turn_count(proj) if proj else 0
        return {
            "project": proj is not None,
            "global": True,
            "project_dir": str(proj) if proj else None,
            "global_dir": str(GLOBAL_DATA_DIR),
            "cwd": str(Path.cwd()),
            "global_turn_count": g_count,
            "project_turn_count": p_count,
        }

    @app.get("/api/turns")
    def get_turns(
        scope: str = "global",
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
        tag: Optional[str] = None,
        mode: str = "keyword",
    ) -> dict:
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        with _memory_for(scope) as mem:
            if mode == "semantic" and q:
                hits = mem.search(q, top_k=page_size, min_score=0.0, source="turns")
                ids = [h["id"] for h in hits]
                items: list[dict] = []
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    rows = mem.db.execute(
                        f"SELECT id, session_id, ts, cwd, user_msg, assistant_msg, "
                        f"summary, summary_source, summary_model, summary_ts "
                        f"FROM turns WHERE id IN ({placeholders})",
                        ids,
                    ).fetchall()
                    by_id = {r["id"]: dict(r) for r in rows}
                    ordered = [by_id[i] for i in ids if i in by_id]
                    mem._attach_tags(ordered)
                    score_by_id = {h["id"]: h["score"] for h in hits}
                    for it in ordered:
                        it["score"] = score_by_id.get(it["id"])
                    items = ordered
                _attach_retrieval_counts(mem, items)
                return {"items": items, "total": len(items), "mode": "semantic"}
            offset = (page - 1) * page_size
            items = mem.list_turns(limit=page_size, offset=offset, query=q, tag=tag)
            total = mem.count_turns(query=q, tag=tag)
            _attach_retrieval_counts(mem, items)
            return {"items": items, "total": total, "mode": "keyword"}

    @app.get("/api/retrievals")
    def get_retrievals(
        scope: str = "global",
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
    ) -> dict:
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        offset = (page - 1) * page_size
        with _memory_for(scope) as mem:
            items = mem.list_retrievals(limit=page_size, offset=offset, query=q)
            total = mem.count_retrievals(query=q)
        return {"items": items, "total": total}

    @app.get("/api/retrievals/{scope}/{retrieval_id}")
    def get_retrieval_detail(scope: str, retrieval_id: str) -> dict:
        with _memory_for(scope) as mem:
            r = mem.get_retrieval(retrieval_id)
            if r is None:
                raise HTTPException(status_code=404, detail="retrieval not found")
            # Group hit turn_ids by their stored scope so we can fetch each from
            # the correct DB. A retrieval may reference turns in either store.
            ids_by_scope: dict[str, list[str]] = {}
            for h in r["hits"]:
                ids_by_scope.setdefault(h.get("scope") or scope, []).append(h["turn_id"])
            # Fetch turns from the same DB first (cheap path).
            turns_map: dict[str, dict] = {}
            same_ids = ids_by_scope.pop(scope, [])
            if same_ids:
                turns_map.update(mem.get_turns_by_ids(same_ids))
        # Fetch turns from other scopes outside the held memory context.
        for other_scope, ids in ids_by_scope.items():
            try:
                with _memory_for(other_scope) as other:
                    turns_map.update(other.get_turns_by_ids(ids))
            except HTTPException:
                continue
        for h in r["hits"]:
            t = turns_map.get(h["turn_id"])
            h["turn"] = t  # may be None if the turn was deleted
        return r

    @app.get("/api/top-referenced")
    def get_top_referenced(scope: str = "global", limit: int = 10) -> dict:
        limit = max(1, min(50, limit))
        with _memory_for(scope) as mem:
            items = mem.top_referenced_turns(limit=limit)
        return {"items": items}

    @app.get("/api/turns/{scope}/{turn_id}/retrievals")
    def get_turn_retrievals(scope: str, turn_id: str) -> dict:
        with _memory_for(scope) as mem:
            items = mem.list_retrievals_for_turn(turn_id)
        return {"items": items, "total": len(items)}

    @app.delete("/api/turns/{scope}/{turn_id}")
    def delete_turn(scope: str, turn_id: str) -> dict:
        with _memory_for(scope) as mem:
            ok = mem.forget(turn_id)
        if not ok:
            raise HTTPException(status_code=404, detail="turn not found")
        return {"ok": True}

    @app.post("/api/turns/{scope}/{turn_id}/tags")
    def add_turn_tag(scope: str, turn_id: str, body: TagBody) -> dict:
        with _memory_for(scope) as mem:
            ok = mem.add_tag(turn_id, body.name, kind=body.kind, source="manual")
        if not ok:
            raise HTTPException(status_code=400, detail="could not add tag")
        return {"ok": True}

    @app.delete("/api/turns/{scope}/{turn_id}/tags/{tag}")
    def remove_turn_tag(scope: str, turn_id: str, tag: str) -> dict:
        with _memory_for(scope) as mem:
            ok = mem.remove_tag(turn_id, tag)
        if not ok:
            raise HTTPException(status_code=404, detail="tag not on turn")
        return {"ok": True}

    @app.post("/api/turns/{scope}/{turn_id}/summary")
    def regenerate_summary(scope: str, turn_id: str) -> dict:
        from .summarizer import summarize_with_source
        from .summarizer import is_enabled

        if not is_enabled():
            raise HTTPException(status_code=400, detail="summarizer disabled (SUMMARY_ENABLED=0)")
        with _memory_for(scope) as mem:
            t = mem.get_turn(turn_id)
        if t is None:
            raise HTTPException(status_code=404, detail="turn not found")

        # The summarizer can block on a CLI/SDK model call. Keep it outside the
        # shared Memory lock so the rest of the Web UI can continue reading.
        result = summarize_with_source(t["user_msg"], t["assistant_msg"])
        if not result:
            raise HTTPException(status_code=502, detail="summarizer failed (check ANTHROPIC_API_KEY)")
        summary, source, used_model = result

        with _memory_for(scope) as mem:
            ok = mem.set_summary(turn_id, summary, source=source, model=used_model)
        if not ok:
            raise HTTPException(status_code=404, detail="turn not found")
        return {
            "ok": True,
            "summary": summary,
            "summary_source": source,
            "summary_model": used_model,
        }

    @app.get("/api/tags")
    def get_tags(scope: str = "global", kind: Optional[str] = None) -> list[dict]:
        with _memory_for(scope) as mem:
            return mem.list_tags(kind=kind)

    @app.post("/api/open-file")
    def open_file(body: OpenFileBody) -> dict:
        raw = body.path.strip()
        if not raw:
            logger.warning("open-file rejected: empty path")
            raise HTTPException(status_code=400, detail="empty path")
        target = Path(raw).expanduser()
        if not target.is_absolute():
            logger.warning("open-file rejected: non-absolute path=%s", raw)
            raise HTTPException(status_code=400, detail="path must be absolute")
        if not target.exists() or not target.is_file():
            logger.warning("open-file rejected: missing file path=%s", target)
            raise HTTPException(status_code=404, detail=f"file not found: {target}")

        line = body.line if (body.line is not None and body.line > 0) else None
        logger.info("open-file request path=%s line=%s", target, line)
        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", str(target)])
                logger.info("open-file success method=open path=%s", target)
                return {"ok": True, "method": "open", "path": str(target), "line": line}
            except Exception as e:
                logger.exception("open-file failed method=open path=%s", target)
                raise HTTPException(status_code=500, detail=f"failed to open file: {e}") from e

        if os.name == "nt":
            try:
                os.startfile(str(target))  # type: ignore[attr-defined]
                logger.info("open-file success method=startfile path=%s", target)
                return {"ok": True, "method": "startfile", "path": str(target), "line": line}
            except Exception as e:
                logger.exception("open-file failed method=startfile path=%s", target)
                raise HTTPException(status_code=500, detail=f"failed to open file: {e}") from e

        if _try_open_with_command(["xdg-open", str(target)]):
            logger.info("open-file success method=xdg-open path=%s", target)
            return {"ok": True, "method": "xdg-open", "path": str(target), "line": line}

        logger.error("open-file failed: no available opener path=%s", target)
        raise HTTPException(status_code=500, detail="no available opener on this system")

    static_dir = _static_dir()
    if static_dir is not None:
        # Mount Vite "assets/" sub-folder + serve index.html on root and SPA fallbacks.
        app.mount(
            "/assets",
            StaticFiles(directory=str(static_dir / "assets")),
            name="assets",
        )

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> FileResponse:
            target = static_dir / path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(static_dir / "index.html")
    else:
        @app.get("/")
        def missing_ui() -> dict:
            return {
                "error": "Web UI assets not built",
                "hint": "Run `cd web && npm install && npm run build` from the repo root.",
            }

    return app


app = create_app()
