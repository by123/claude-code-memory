import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api";
import type { Scope, Turn, TurnRetrievalsResponse } from "../types";

interface Props {
  turn: Turn;
  scope: Scope;
  onDelete: () => void;
  onAddTag: (name: string) => void;
  onRemoveTag: (name: string) => void;
}

function fmtTs(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener" />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export function TurnCard({ turn, scope, onDelete, onAddTag, onRemoveTag }: Props) {
  const [newTag, setNewTag] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [showRetrievals, setShowRetrievals] = useState(false);
  const [retrievals, setRetrievals] = useState<TurnRetrievalsResponse | null>(null);
  const [retrErr, setRetrErr] = useState<string | null>(null);

  useEffect(() => {
    if (!showRetrievals || retrievals !== null) return;
    let cancelled = false;
    api
      .turnRetrievals(scope, turn.id)
      .then((d) => !cancelled && setRetrievals(d))
      .catch((e) => !cancelled && setRetrErr(String(e)));
    return () => {
      cancelled = true;
    };
  }, [showRetrievals, retrievals, scope, turn.id]);

  const userPreview =
    !expanded && turn.user_msg.length > 400
      ? turn.user_msg.slice(0, 400) + "…"
      : turn.user_msg;
  const asstPreview =
    !expanded && turn.assistant_msg.length > 800
      ? turn.assistant_msg.slice(0, 800) + "…"
      : turn.assistant_msg;
  const truncated =
    turn.user_msg.length > 400 || turn.assistant_msg.length > 800;

  const submitTag = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTag.trim()) return;
    onAddTag(newTag);
    setNewTag("");
  };

  return (
    <li className="turn">
      <div className="turn-head">
        <div className="ts">
          {fmtTs(turn.ts)}
          {typeof turn.score === "number" && (
            <span className="score"> · score {turn.score.toFixed(3)}</span>
          )}
          {typeof turn.retrieval_count === "number" && turn.retrieval_count > 0 && (
            <button
              className="ref-badge"
              title="点击查看哪些后续提问引用了这条对话"
              onClick={() => setShowRetrievals((x) => !x)}
            >
              被引用 {turn.retrieval_count} 次
            </button>
          )}
        </div>
        <button className="danger" onClick={onDelete}>
          delete
        </button>
      </div>

      <div className="msg msg-user">
        <div className="avatar" aria-hidden>U</div>
        <div className="bubble">
          <div className="bubble-head">User</div>
          <Markdown text={userPreview} />
        </div>
      </div>
      <div className="msg msg-assistant">
        <div className="avatar" aria-hidden>✦</div>
        <div className="bubble">
          <div className="bubble-head">Assistant</div>
          <Markdown text={asstPreview} />
        </div>
      </div>

      {truncated && (
        <button className="link" onClick={() => setExpanded((x) => !x)}>
          {expanded ? "collapse" : "expand"}
        </button>
      )}

      <div className="tags-row">
        {turn.tags.map((t) => (
          <span key={t} className="tag-chip">
            #{t}
            <button title="remove tag" onClick={() => onRemoveTag(t)}>
              ×
            </button>
          </span>
        ))}
        <form onSubmit={submitTag} className="add-tag">
          <input
            placeholder="+ tag"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
          />
        </form>
      </div>

      {showRetrievals && (
        <div className="ref-panel">
          <div className="block-title">后续提问引用了这条对话</div>
          {retrErr && <div className="error">{retrErr}</div>}
          {!retrErr && retrievals === null && <div className="empty">loading…</div>}
          {retrievals && retrievals.items.length === 0 && (
            <div className="empty">暂无引用</div>
          )}
          {retrievals && retrievals.items.length > 0 && (
            <ul className="ref-list">
              {retrievals.items.map((r) => (
                <li key={r.id}>
                  <span className="ts">{fmtTs(r.ts)}</span>
                  <span className="score">score {r.score.toFixed(3)}</span>
                  <span className="ref-prompt">
                    {r.prompt.length > 120 ? r.prompt.slice(0, 120) + "…" : r.prompt}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

    </li>
  );
}
