"""SQLite (source of truth) + Chroma (vector index)."""
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings

from .config import GLOBAL_DATA_DIR, ensure_dirs, paths_for
from .embeddings import embed_one

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    cwd TEXT
);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts REAL NOT NULL,
    cwd TEXT,
    user_msg TEXT NOT NULL,
    assistant_msg TEXT NOT NULL,
    user_uuid TEXT
);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts REAL NOT NULL,
    summary TEXT NOT NULL,
    turn_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
CREATE INDEX IF NOT EXISTS idx_summaries_session ON summaries(session_id);
CREATE TABLE IF NOT EXISTS tags (
    name TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turn_tags (
    turn_id TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    PRIMARY KEY (turn_id, tag_name)
);
CREATE INDEX IF NOT EXISTS idx_turn_tags_turn ON turn_tags(turn_id);
CREATE INDEX IF NOT EXISTS idx_turn_tags_tag ON turn_tags(tag_name);
CREATE TABLE IF NOT EXISTS retrievals (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    session_id TEXT,
    cwd TEXT,
    prompt TEXT NOT NULL,
    scope_used TEXT,
    hit_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS retrieval_hits (
    retrieval_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    scope TEXT,
    kind TEXT,
    score REAL,
    rank INTEGER,
    PRIMARY KEY (retrieval_id, turn_id)
);
CREATE INDEX IF NOT EXISTS idx_retrievals_ts ON retrievals(ts);
CREATE INDEX IF NOT EXISTS idx_retrieval_hits_turn ON retrieval_hits(turn_id);
"""


class Memory:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or GLOBAL_DATA_DIR
        paths = paths_for(self.data_dir)
        ensure_dirs(self.data_dir)
        paths["chroma_dir"].mkdir(parents=True, exist_ok=True)

        self.db_path = paths["db_path"]
        self.chroma_dir = paths["chroma_dir"]

        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(turns)")}
        if "user_uuid" not in cols:
            self.db.execute("ALTER TABLE turns ADD COLUMN user_uuid TEXT")
        self.db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_turns_user_uuid "
            "ON turns(session_id, user_uuid) WHERE user_uuid IS NOT NULL"
        )
        self.db.commit()

        self.chroma = chromadb.PersistentClient(
            path=str(self.chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.turns = self.chroma.get_or_create_collection(
            "turns", embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
        self.summaries = self.chroma.get_or_create_collection(
            "summaries", embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    # ---------- sessions ----------
    def ensure_session(self, session_id: str, cwd: Optional[str] = None) -> None:
        cur = self.db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if cur.fetchone():
            return
        self.db.execute(
            "INSERT INTO sessions(id, started_at, cwd) VALUES(?,?,?)",
            (session_id, time.time(), cwd),
        )
        self.db.commit()

    def end_session(self, session_id: str) -> None:
        self.db.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (time.time(), session_id),
        )
        self.db.commit()

    # ---------- turns ----------
    def add_turn(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        cwd: Optional[str] = None,
    ) -> str:
        turn_id = str(uuid.uuid4())
        ts = time.time()
        self.db.execute(
            "INSERT INTO turns(id, session_id, ts, cwd, user_msg, assistant_msg) VALUES(?,?,?,?,?,?)",
            (turn_id, session_id, ts, cwd, user_msg, assistant_msg),
        )
        self.db.commit()

        doc = f"User: {user_msg}\n\nAssistant: {assistant_msg}"
        vec = embed_one(doc, input_type="document")
        self.turns.add(
            ids=[turn_id],
            embeddings=[vec],
            documents=[doc],
            metadatas=[{"session_id": session_id, "ts": ts, "cwd": cwd or ""}],
        )
        return turn_id

    def upsert_turn(
        self,
        session_id: str,
        user_uuid: str,
        user_msg: str,
        assistant_msg: str,
        cwd: Optional[str] = None,
    ) -> tuple:
        row = self.db.execute(
            "SELECT id, assistant_msg FROM turns WHERE session_id = ? AND user_uuid = ?",
            (session_id, user_uuid),
        ).fetchone()
        ts = time.time()

        if row is None:
            turn_id = str(uuid.uuid4())
            self.db.execute(
                "INSERT INTO turns(id, session_id, ts, cwd, user_msg, assistant_msg, user_uuid) "
                "VALUES(?,?,?,?,?,?,?)",
                (turn_id, session_id, ts, cwd, user_msg, assistant_msg, user_uuid),
            )
            self.db.commit()
            action = "insert"
        else:
            turn_id = row["id"]
            if row["assistant_msg"] == assistant_msg:
                return turn_id, "skip"
            self.db.execute(
                "UPDATE turns SET assistant_msg = ?, ts = ?, user_msg = ?, cwd = ? WHERE id = ?",
                (assistant_msg, ts, user_msg, cwd, turn_id),
            )
            self.db.commit()
            action = "update"

        doc = f"User: {user_msg}\n\nAssistant: {assistant_msg}"
        vec = embed_one(doc, input_type="document")
        meta = {"session_id": session_id, "ts": ts, "cwd": cwd or ""}
        if action == "insert":
            self.turns.add(ids=[turn_id], embeddings=[vec], documents=[doc], metadatas=[meta])
        else:
            self.turns.upsert(ids=[turn_id], embeddings=[vec], documents=[doc], metadatas=[meta])
        return turn_id, action

    # ---------- summaries ----------
    def add_summary(self, session_id: str, summary: str, turn_count: int) -> str:
        sid = str(uuid.uuid4())
        ts = time.time()
        self.db.execute(
            "INSERT INTO summaries(id, session_id, ts, summary, turn_count) VALUES(?,?,?,?,?)",
            (sid, session_id, ts, summary, turn_count),
        )
        self.db.commit()
        vec = embed_one(summary, input_type="document")
        self.summaries.add(
            ids=[sid],
            embeddings=[vec],
            documents=[summary],
            metadatas=[{"session_id": session_id, "ts": ts}],
        )
        return sid

    # ---------- search ----------
    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
        source: str = "both",
    ) -> List[Dict[str, Any]]:
        qvec = embed_one(query, input_type="query")
        out: List[Dict[str, Any]] = []

        def _pull(collection, kind: str) -> None:
            n = collection.count()
            if n == 0:
                return
            res = collection.query(
                query_embeddings=[qvec],
                n_results=min(top_k, n),
            )
            ids = res["ids"][0]
            docs = res["documents"][0]
            metas = res["metadatas"][0]
            dists = res["distances"][0]
            for i, d, m, dist in zip(ids, docs, metas, dists):
                score = 1.0 - float(dist)
                if score < min_score:
                    continue
                out.append(
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

        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:top_k]

    # ---------- admin ----------
    def stats(self) -> Dict[str, int]:
        n_sessions = self.db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        n_turns = self.db.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        n_sum = self.db.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        return {
            "sessions": n_sessions,
            "turns": n_turns,
            "summaries": n_sum,
            "chroma_turns": self.turns.count(),
            "chroma_summaries": self.summaries.count(),
        }

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, session_id, ts, user_msg, assistant_msg FROM turns ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- browser-style listing & tags ----------
    def _attach_tags(self, turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not turns:
            return turns
        ids = [t["id"] for t in turns]
        placeholders = ",".join("?" for _ in ids)
        rows = self.db.execute(
            f"SELECT turn_id, tag_name FROM turn_tags WHERE turn_id IN ({placeholders})",
            ids,
        ).fetchall()
        by_id: Dict[str, List[str]] = {i: [] for i in ids}
        for r in rows:
            by_id[r["turn_id"]].append(r["tag_name"])
        for t in turns:
            t["tags"] = sorted(by_id.get(t["id"], []))
        return turns

    def list_turns(
        self,
        limit: int = 20,
        offset: int = 0,
        query: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = (
            "SELECT t.id, t.session_id, t.ts, t.cwd, t.user_msg, t.assistant_msg "
            "FROM turns t"
        )
        params: list = []
        wheres: list = []
        if tag:
            sql += " JOIN turn_tags tt ON tt.turn_id = t.id"
            wheres.append("tt.tag_name = ?")
            params.append(tag)
        if query:
            wheres.append("(t.user_msg LIKE ? OR t.assistant_msg LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY t.ts DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = [dict(r) for r in self.db.execute(sql, params).fetchall()]
        return self._attach_tags(rows)

    def count_turns(self, query: Optional[str] = None, tag: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM turns t"
        params: list = []
        wheres: list = []
        if tag:
            sql += " JOIN turn_tags tt ON tt.turn_id = t.id"
            wheres.append("tt.tag_name = ?")
            params.append(tag)
        if query:
            wheres.append("(t.user_msg LIKE ? OR t.assistant_msg LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        return int(self.db.execute(sql, params).fetchone()[0])

    def list_tags(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT t.name, t.created_at, COUNT(tt.turn_id) AS count "
            "FROM tags t LEFT JOIN turn_tags tt ON tt.tag_name = t.name "
            "GROUP BY t.name ORDER BY count DESC, t.name"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_tag(self, turn_id: str, tag: str) -> bool:
        tag = tag.strip().lstrip("#")
        if not tag:
            return False
        row = self.db.execute("SELECT id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None:
            return False
        self.db.execute(
            "INSERT OR IGNORE INTO tags(name, created_at) VALUES(?, ?)",
            (tag, time.time()),
        )
        cur = self.db.execute(
            "INSERT OR IGNORE INTO turn_tags(turn_id, tag_name) VALUES(?, ?)",
            (turn_id, tag),
        )
        self.db.commit()
        return cur.rowcount > 0

    def remove_tag(self, turn_id: str, tag: str) -> bool:
        tag = tag.strip().lstrip("#")
        cur = self.db.execute(
            "DELETE FROM turn_tags WHERE turn_id = ? AND tag_name = ?",
            (turn_id, tag),
        )
        self.db.commit()
        # Garbage-collect a tag with no remaining attachments.
        if cur.rowcount > 0:
            left = self.db.execute(
                "SELECT 1 FROM turn_tags WHERE tag_name = ? LIMIT 1", (tag,)
            ).fetchone()
            if left is None:
                self.db.execute("DELETE FROM tags WHERE name = ?", (tag,))
                self.db.commit()
        return cur.rowcount > 0

    def get_session_turns(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, ts, user_msg, assistant_msg FROM turns WHERE session_id = ? ORDER BY ts",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def forget(self, turn_id: str) -> bool:
        affected_tags = [
            r["tag_name"]
            for r in self.db.execute(
                "SELECT tag_name FROM turn_tags WHERE turn_id = ?", (turn_id,)
            ).fetchall()
        ]
        self.db.execute("DELETE FROM turn_tags WHERE turn_id = ?", (turn_id,))
        self.db.execute("DELETE FROM retrieval_hits WHERE turn_id = ?", (turn_id,))
        cur = self.db.execute("DELETE FROM turns WHERE id = ?", (turn_id,))
        # Garbage-collect any tag that no longer has attachments.
        for tag in affected_tags:
            left = self.db.execute(
                "SELECT 1 FROM turn_tags WHERE tag_name = ? LIMIT 1", (tag,)
            ).fetchone()
            if left is None:
                self.db.execute("DELETE FROM tags WHERE name = ?", (tag,))
        self.db.commit()
        if cur.rowcount == 0:
            cur2 = self.db.execute("DELETE FROM summaries WHERE id = ?", (turn_id,))
            self.db.commit()
            if cur2.rowcount == 0:
                return False
            try:
                self.summaries.delete(ids=[turn_id])
            except Exception:
                pass
            return True
        try:
            self.turns.delete(ids=[turn_id])
        except Exception:
            pass
        return True

    # ---------- retrievals ----------
    def record_retrieval(
        self,
        prompt: str,
        hits: List[Dict[str, Any]],
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        scope_used: Optional[str] = None,
    ) -> str:
        rid = str(uuid.uuid4())
        ts = time.time()
        self.db.execute(
            "INSERT INTO retrievals(id, ts, session_id, cwd, prompt, scope_used, hit_count) "
            "VALUES(?,?,?,?,?,?,?)",
            (rid, ts, session_id, cwd, prompt, scope_used, len(hits)),
        )
        for rank, h in enumerate(hits):
            self.db.execute(
                "INSERT OR IGNORE INTO retrieval_hits(retrieval_id, turn_id, scope, kind, score, rank) "
                "VALUES(?,?,?,?,?,?)",
                (
                    rid,
                    h.get("id"),
                    h.get("scope"),
                    h.get("kind"),
                    float(h.get("score") or 0.0),
                    rank,
                ),
            )
        self.db.commit()
        return rid

    def list_retrievals(
        self,
        limit: int = 20,
        offset: int = 0,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT id, ts, session_id, cwd, prompt, scope_used, hit_count FROM retrievals"
        params: list = []
        if query:
            sql += " WHERE prompt LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY ts DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def count_retrievals(self, query: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM retrievals"
        params: list = []
        if query:
            sql += " WHERE prompt LIKE ?"
            params.append(f"%{query}%")
        return int(self.db.execute(sql, params).fetchone()[0])

    def get_retrieval(self, retrieval_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            "SELECT id, ts, session_id, cwd, prompt, scope_used, hit_count "
            "FROM retrievals WHERE id = ?",
            (retrieval_id,),
        ).fetchone()
        if row is None:
            return None
        out = dict(row)
        hits = [
            dict(r)
            for r in self.db.execute(
                "SELECT turn_id, scope, kind, score, rank FROM retrieval_hits "
                "WHERE retrieval_id = ? ORDER BY rank",
                (retrieval_id,),
            ).fetchall()
        ]
        out["hits"] = hits
        return out

    def hit_counts_for_turns(self, turn_ids: List[str]) -> Dict[str, int]:
        if not turn_ids:
            return {}
        placeholders = ",".join("?" for _ in turn_ids)
        rows = self.db.execute(
            f"SELECT turn_id, COUNT(*) AS c FROM retrieval_hits "
            f"WHERE turn_id IN ({placeholders}) GROUP BY turn_id",
            turn_ids,
        ).fetchall()
        return {r["turn_id"]: int(r["c"]) for r in rows}

    def top_referenced_turns(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT t.id, t.session_id, t.ts, t.cwd, t.user_msg, t.assistant_msg, "
            "COUNT(h.retrieval_id) AS retrieval_count "
            "FROM turns t JOIN retrieval_hits h ON h.turn_id = t.id "
            "GROUP BY t.id "
            "ORDER BY retrieval_count DESC, t.ts DESC "
            "LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        items = [dict(r) for r in rows]
        return self._attach_tags(items)

    def list_retrievals_for_turn(
        self, turn_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT r.id, r.ts, r.session_id, r.cwd, r.prompt, r.scope_used, r.hit_count, "
            "h.score, h.rank "
            "FROM retrieval_hits h JOIN retrievals r ON r.id = h.retrieval_id "
            "WHERE h.turn_id = ? ORDER BY r.ts DESC LIMIT ?",
            (turn_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_turns_by_ids(self, turn_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not turn_ids:
            return {}
        placeholders = ",".join("?" for _ in turn_ids)
        rows = self.db.execute(
            f"SELECT id, session_id, ts, cwd, user_msg, assistant_msg "
            f"FROM turns WHERE id IN ({placeholders})",
            turn_ids,
        ).fetchall()
        return {r["id"]: dict(r) for r in rows}

    def close(self) -> None:
        self.db.close()


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

    Each result is annotated with a `scope` field ("project" | "global").
    """
    from .config import GLOBAL_DATA_DIR, find_project_root

    proj_dir = find_project_root(cwd) if cwd else None
    if scope == "auto":
        scope = "project" if proj_dir else "global"

    targets: List = []
    if scope in ("project", "merged") and proj_dir is not None:
        targets.append(("project", proj_dir))
    if scope in ("global", "merged"):
        targets.append(("global", GLOBAL_DATA_DIR))

    out: List[Dict[str, Any]] = []
    for label, ddir in targets:
        m = Memory(data_dir=ddir)
        try:
            for r in m.search(query, top_k=top_k, min_score=min_score):
                r["scope"] = label
                out.append(r)
        finally:
            m.close()
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top_k]
