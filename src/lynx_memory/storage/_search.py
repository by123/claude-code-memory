"""Vector + tag-aware search over a single Memory store."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..embeddings import embed_one

logger = logging.getLogger(__name__)


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
        import os
        backend = os.environ.get("EMBEDDING_BACKEND", "voyage")
        model = (
            os.environ.get("VOYAGE_MODEL", "voyage-3.5") if backend == "voyage"
            else os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        )
        logger.info("[search] backend=%s model=%s top_k=%d min_score=%.2f query=%r",
                    backend, model, top_k, min_score, query[:80])

        qvec = embed_one(query, input_type="query")
        fetch_k = max(self._SEARCH_MIN_CANDIDATES, top_k * self._SEARCH_OVERFETCH)
        candidates: List[Dict[str, Any]] = []

        def _pull(collection, kind: str) -> None:
            n = collection.count()
            logger.info("[search] collection=%s total_docs=%d fetch_k=%d", kind, n, fetch_k)
            if n == 0:
                return
            res = collection.query(
                query_embeddings=[qvec],
                n_results=min(fetch_k, n),
            )
            all_scores = []
            for i, d, m, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
            ):
                score = 1.0 - float(dist)
                all_scores.append(score)
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
            scores_str = ", ".join(f"{s:.3f}" for s in all_scores)
            passed = sum(1 for s in all_scores if s >= min_score)
            logger.info("[search] collection=%s scores=[%s] passed_min_score=%d/%d",
                        kind, scores_str, passed, len(all_scores))

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
        final = candidates[:top_k]
        logger.info("[search] returning %d result(s): %s",
                    len(final),
                    [(r["kind"], f"{r['score']:.3f}") for r in final])
        return final
