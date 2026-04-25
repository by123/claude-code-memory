"""SQLite (source of truth) + Chroma (vector index)."""
import sqlite3
import time
import uuid
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings

from .config import DB_PATH, CHROMA_DIR, ensure_dirs
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
"""


class Memory:
    def __init__(self) -> None:
        ensure_dirs()
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)
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
            path=str(CHROMA_DIR),
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

    def get_session_turns(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, ts, user_msg, assistant_msg FROM turns WHERE session_id = ? ORDER BY ts",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def forget(self, turn_id: str) -> bool:
        cur = self.db.execute("DELETE FROM turns WHERE id = ?", (turn_id,))
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

    def close(self) -> None:
        self.db.close()
