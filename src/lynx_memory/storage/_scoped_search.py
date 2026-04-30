"""Scope-aware search across project + global stores."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def search_scoped(
    query: str,
    cwd: Optional[str] = None,
    scope: str = "auto",
    top_k: int = 5,
    min_score: float = 0.3,
) -> List[Dict[str, Any]]:
    """Scope-aware search across project and/or global stores.

    scope:
      - "auto"    : project store if cwd is inside a project, else global
      - "project" : project store only (empty results if no project)
      - "global"  : global store only
      - "merged"  : query both stores and combine results

    When merging, each non-empty store gets a guaranteed reserved slot in
    the final top_k so a high-volume store can't completely shadow the other.
    Each result is annotated with a `scope` field ("project" | "global").
    """
    from ..config import GLOBAL_DATA_DIR, find_project_root
    from . import Memory

    proj_dir = find_project_root(cwd) if cwd else None
    if scope == "auto":
        scope = "project" if proj_dir else "global"

    targets: List = []
    if scope in ("project", "merged") and proj_dir is not None:
        targets.append(("project", proj_dir))
    if scope in ("global", "merged"):
        targets.append(("global", GLOBAL_DATA_DIR))

    n_targets = len(targets)
    if n_targets <= 1:
        per_store_k = top_k
    else:
        per_store_k = max(2, top_k)

    pooled: List[Dict[str, Any]] = []
    per_store_results: Dict[str, List[Dict[str, Any]]] = {}
    for label, ddir in targets:
        m = Memory(data_dir=ddir)
        try:
            results = m.search(query, top_k=per_store_k, min_score=min_score)
        finally:
            m.close()
        for r in results:
            r["scope"] = label
        per_store_results[label] = results
        pooled.extend(results)

    pooled.sort(key=lambda x: x["score"], reverse=True)
    if n_targets <= 1:
        return pooled[:top_k]

    # Reserve at least one slot per non-empty store; fill the rest by score.
    reserved_per_store = max(1, top_k // (n_targets * 2))
    selected: List[Dict[str, Any]] = []
    seen: set = set()
    for label, results in per_store_results.items():
        for r in results[:reserved_per_store]:
            key = (label, r["id"])
            if key in seen:
                continue
            seen.add(key)
            selected.append(r)
            if len(selected) >= top_k:
                break
        if len(selected) >= top_k:
            break
    for r in pooled:
        if len(selected) >= top_k:
            break
        key = (r["scope"], r["id"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(r)
    selected.sort(key=lambda x: x["score"], reverse=True)
    return selected
