import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api";
import type { RetrievalDetail, RetrievalSummary, Scope, Turn } from "../types";

const PAGE_SIZE = 15;

function fmtTs(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

function clip(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

interface DetailProps {
  scope: Scope;
  retrievalId: string;
}

function RetrievalDetailPanel({ scope, retrievalId }: DetailProps) {
  const [data, setData] = useState<RetrievalDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .retrievalDetail(scope, retrievalId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [scope, retrievalId]);

  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="empty">loading…</div>;

  return (
    <div className="retrieval-detail">
      <div className="block-title">命中的历史对话（{data.hits.length}）</div>
      {data.hits.length === 0 && <div className="empty">no hits</div>}
      <ul className="hit-list">
        {data.hits.map((h) => (
          <li key={h.turn_id} className="hit">
            <div className="hit-head">
              <span className="rank">#{h.rank + 1}</span>
              <span className="score">score {h.score.toFixed(3)}</span>
              {h.scope && <span className="hit-scope">{h.scope}</span>}
              {h.kind && <span className="hit-scope">{h.kind}</span>}
            </div>
            {h.turn ? (
              <div className="hit-body">
                <div className="ts">{fmtTs(h.turn.ts)}</div>
                <div className="hit-snippet">
                  <strong>U: </strong>
                  {clip(h.turn.user_msg, 240)}
                </div>
                <div className="hit-snippet">
                  <strong>A: </strong>
                  <span className="md inline">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {clip(h.turn.assistant_msg, 360)}
                    </ReactMarkdown>
                  </span>
                </div>
              </div>
            ) : (
              <div className="empty">turn 已删除（{h.turn_id.slice(0, 8)}…）</div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function TurnModal({ turn, onClose }: { turn: Turn; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="close">
          ×
        </button>
        <div className="modal-meta">
          <span>{fmtTs(turn.ts)}</span>
          {typeof turn.retrieval_count === "number" && (
            <span className="modal-count">被引用 {turn.retrieval_count} 次</span>
          )}
        </div>
        <div className="msg msg-user">
          <div className="avatar" aria-hidden>
            U
          </div>
          <div className="bubble">
            <div className="bubble-head">User</div>
            <div className="md">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.user_msg}</ReactMarkdown>
            </div>
          </div>
        </div>
        <div className="msg msg-assistant">
          <div className="avatar" aria-hidden>
            ✦
          </div>
          <div className="bubble">
            <div className="bubble-head">Assistant</div>
            <div className="md">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.assistant_msg}</ReactMarkdown>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface Props {
  scope: Scope;
}

export function RetrievalsView({ scope }: Props) {
  const [items, setItems] = useState<RetrievalSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const [topItems, setTopItems] = useState<Turn[]>([]);
  const [topLoading, setTopLoading] = useState(false);
  const [modalTurn, setModalTurn] = useState<Turn | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .retrievals({ scope, page, pageSize: PAGE_SIZE, q: submittedQuery || undefined })
      .then((r) => {
        if (cancelled) return;
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e));
        setItems([]);
        setTotal(0);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [scope, page, submittedQuery]);

  useEffect(() => {
    let cancelled = false;
    setTopLoading(true);
    api
      .topReferenced(scope, 10)
      .then((r) => !cancelled && setTopItems(r.items))
      .catch(() => !cancelled && setTopItems([]))
      .finally(() => !cancelled && setTopLoading(false));
    return () => {
      cancelled = true;
    };
  }, [scope]);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSubmittedQuery(query.trim());
  };

  const onClear = () => {
    setQuery("");
    setSubmittedQuery("");
    setPage(1);
  };

  const promptPreview = (s: string) => clip(s.replace(/\s+/g, " "), 60);

  return (
    <>
      <aside className="sidebar">
        <form className="search" onSubmit={onSubmit}>
          <input
            placeholder="Search prompts…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="search-actions">
            <button type="submit">Search</button>
            <button type="button" onClick={onClear}>
              Clear
            </button>
          </div>
        </form>

        <div className="topref-block">
          <div className="block-title">
            <span>Top Referenced</span>
            <span className="block-sub">被引用最多的对话</span>
          </div>
          {topLoading && <div className="empty">loading…</div>}
          {!topLoading && topItems.length === 0 && (
            <div className="empty">no references yet</div>
          )}
          <ol className="topref-list">
            {topItems.map((t, i) => (
              <li key={t.id}>
                <button className="topref-item" onClick={() => setModalTurn(t)}>
                  <span className="topref-rank">{i + 1}</span>
                  <span className="topref-text">{promptPreview(t.user_msg)}</span>
                  <span className="topref-count" title="被引用次数">
                    {t.retrieval_count ?? 0}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      </aside>

      <section className="content">
        <div className="status">
          <span>
            {total} retrieval{total === 1 ? "" : "s"}
            {submittedQuery ? ` · "${submittedQuery}"` : ""}
          </span>
          {loading && <span className="loading">loading…</span>}
        </div>

        {error && <div className="error">{error}</div>}

        <ul className="turns">
          {items.map((r) => {
            const open = openId === r.id;
            return (
              <li key={r.id} className="turn retrieval-row">
                <div className="turn-head">
                  <div className="ts">
                    {fmtTs(r.ts)}
                    <span className="score">
                      {" · "}
                      {r.hit_count} hit{r.hit_count === 1 ? "" : "s"}
                    </span>
                    {r.scope_used && <span className="hit-scope">{r.scope_used}</span>}
                  </div>
                  <button className="link" onClick={() => setOpenId(open ? null : r.id)}>
                    {open ? "collapse" : "expand"}
                  </button>
                </div>
                <div className="msg msg-user">
                  <div className="avatar" aria-hidden>?</div>
                  <div className="bubble">
                    <div className="bubble-head">Prompt</div>
                    <div className="md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {open ? r.prompt : clip(r.prompt, 320)}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
                {open && <RetrievalDetailPanel scope={scope} retrievalId={r.id} />}
              </li>
            );
          })}
        </ul>

        {!loading && items.length === 0 && <div className="empty">no retrievals yet.</div>}

        {totalPages > 1 && (
          <div className="pagination">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              ← prev
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              next →
            </button>
          </div>
        )}
      </section>

      {modalTurn && <TurnModal turn={modalTurn} onClose={() => setModalTurn(null)} />}
    </>
  );
}
