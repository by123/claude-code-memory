import { useState } from "react";
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

      <div className="msg">
        <div className="role">User</div>
        <pre>{userPreview}</pre>
      </div>
      <div className="msg">
        <div className="role">Assistant</div>
        <pre>{asstPreview}</pre>
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
