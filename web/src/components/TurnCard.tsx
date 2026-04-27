import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Turn } from "../types";

interface Props {
  turn: Turn;
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

export function TurnCard({ turn, onDelete, onAddTag, onRemoveTag }: Props) {
  const [newTag, setNewTag] = useState("");
  const [expanded, setExpanded] = useState(false);

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

      {turn.cwd && <div className="cwd">cwd: {turn.cwd}</div>}
    </li>
  );
}
