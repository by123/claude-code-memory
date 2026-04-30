"""Vector + tag-aware search over a single Memory store."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..embeddings import embed_one


class _SearchMixin:
    # Over-fetch factor: pull 3x candidates from the vector index before
    # applying tag-kind boosts, so a low-rank-but-high-tag-weight result
    # isn't trimmed away before its boost is applied.
    _SEARCH_OVERFETCH = 3
    _SEARCH_MIN_CANDIDATES = 15

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
        source: str = "both",
    ) -> List[Dict[str, Any]]:
        qvec = embed_one(query, input_type="query")
        fetch_k = max(self._SEARCH_MIN_CANDIDATES, top_k * self._SEARCH_OVERFETCH)
        candidates: List[Dict[str, Any]] = []

        def _pull(collection, kind: str) -> None:
            n = collection.count()
            if n == 0:
                return
            res = collection.query(
                query_embeddings=[qvec],
                n_results=min(fetch_k, n),
            )
            for i, d, m, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
            ):
                score = 1.0 - float(dist)
                if score < min_score:
                    continue
                candidates.append(
                    {
                        "id": i,
                        "kind": kind,
                        "text": d,
                        "score": score,
                        "ts": m.get("ts"),
                        "session_id": m.get("session_id"),
                        "cwd": m.get("cwd", ""),
                    }
                )

        if source in ("both", "turns"):
            _pull(self.turns, "turn")
        if source in ("both", "summaries"):
            _pull(self.summaries, "summary")

        # Apply tag-kind boost BEFORE the final trim so high-weight memories
        # (user.role, user.preference, ...) can climb past raw-score-only hits.
        turn_ids = [r["id"] for r in candidates if r["kind"] == "turn"]
        summaries_by_turn: Dict[str, Optional[str]] = {}
        kinds_by_turn: Dict[str, List[str]] = {}
        if turn_ids:
            placeholders = ",".join("?" for _ in turn_ids)
            for row in self.db.execute(
                f"SELECT id, summary FROM turns WHERE id IN ({placeholders})",
                turn_ids,
            ):
                summaries_by_turn[row["id"]] = row["summary"]
            for row in self.db.execute(
                f"SELECT tt.turn_id, tg.kind "
                f"FROM turn_tags tt JOIN tags tg ON tg.name = tt.tag_name "
                f"WHERE tt.turn_id IN ({placeholders})",
                turn_ids,
            ):
                kinds_by_turn.setdefault(row["turn_id"], []).append(row["kind"] or "custom")

        for r in candidates:
            if r["kind"] != "turn":
                continue
            r["summary"] = summaries_by_turn.get(r["id"])
            tag_kinds = sorted(set(kinds_by_turn.get(r["id"], [])))
            boost = self._tag_weight_for_kinds(tag_kinds)
            r["base_score"] = r["score"]
            r["tag_kinds"] = tag_kinds
            r["memory_weight"] = boost
            r["score"] = min(1.0, float(r["score"]) + boost)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]
