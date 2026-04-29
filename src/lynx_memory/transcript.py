"""Shared transcript parsing + turn persistence for Stop / UserPromptSubmit hooks."""
import json
import os

from .config import paths_for, resolve_data_dir
from .storage import Memory


def read_transcript(path: str) -> list:
    msgs = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return msgs


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                parts.append(block.get("text", ""))
            elif t == "tool_use":
                parts.append(f"[tool_use: {block.get('name', '')}]")
            elif t == "tool_result":
                r = block.get("content", "")
                if isinstance(r, list):
                    r = " ".join(
                        b.get("text", "") if isinstance(b, dict) else str(b)
                        for b in r
                    )
                parts.append(f"[tool_result: {str(r)[:200]}]")
        return "\n".join(p for p in parts if p)
    return str(content)


def _extract_assistant(content) -> tuple:
    if isinstance(content, str):
        return content, ""
    text_parts = []
    tool_parts = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                txt = block.get("text", "")
                if txt:
                    text_parts.append(txt)
            elif t == "tool_use":
                tool_parts.append(f"[tool_use: {block.get('name', '')}]")
    return "\n".join(text_parts), "\n".join(tool_parts)


def _is_codex_transcript(path: str) -> bool:
    """Codex rollout files live under ~/.codex/sessions/.../rollout-*.jsonl."""
    return "/.codex/sessions/" in path or "/sessions/" in path and "/rollout-" in path


def _codex_text(content) -> tuple:
    """Extract (text, tool_marker) from a Codex `payload.content` list.

    Codex content blocks: {"type": "input_text"|"output_text", "text": "..."}.
    """
    if isinstance(content, str):
        return content, ""
    text_parts = []
    tool_parts = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t in ("input_text", "output_text"):
                txt = block.get("text", "")
                if txt:
                    text_parts.append(txt)
            elif t == "tool_use" or (isinstance(t, str) and t.startswith("tool")):
                tool_parts.append(f"[tool: {block.get('name', t)}]")
    return "\n".join(text_parts), "\n".join(tool_parts)


def find_last_turn_codex(msgs: list) -> tuple:
    """Codex rollout JSONL → (user_text, user_uuid, asst_text, asst_uuid, had_prose).

    Codex line shape: {"type": "response_item", "payload": {"type": "message",
    "role": "user|assistant|developer", "content": [...]}, "timestamp": "..."}.
    Each turn has a stable `turn_id` exposed via `event_msg` lines (task_started,
    task_complete) — we use it as the UUID for both halves of the turn.

    Walking backward, we pick the last *real* user prompt: skip developer role
    and skip the env-context user message that Codex injects on session start
    (its text starts with "<environment_context>").
    """
    last_user_idx = None
    user_text = None
    last_user_turn_id = None

    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("type") != "response_item":
            continue
        p = m.get("payload") or {}
        if p.get("type") != "message" or p.get("role") != "user":
            continue
        text, _ = _codex_text(p.get("content", ""))
        if not text:
            continue
        stripped = text.lstrip()
        if stripped.startswith("<environment_context>"):
            continue
        user_text = text
        last_user_idx = i
        break

    if last_user_idx is None:
        return None, None, None, None, False

    # Find the turn_id by scanning forward for a turn_context / event_msg.
    for j in range(last_user_idx, len(msgs)):
        m = msgs[j]
        p = m.get("payload") or {}
        tid = p.get("turn_id")
        if tid:
            last_user_turn_id = tid
            break
    if last_user_turn_id is None:
        # Fallback: scan backward.
        for j in range(last_user_idx - 1, -1, -1):
            p = (msgs[j].get("payload") or {})
            if p.get("turn_id"):
                last_user_turn_id = p["turn_id"]
                break
    if last_user_turn_id is None:
        last_user_turn_id = f"codex-idx{last_user_idx}"

    text_parts: list[str] = []
    tool_parts: list[str] = []
    last_a_turn_id = None
    for j in range(last_user_idx + 1, len(msgs)):
        m = msgs[j]
        if m.get("type") != "response_item":
            continue
        p = m.get("payload") or {}
        if p.get("type") != "message" or p.get("role") != "assistant":
            continue
        t, tools = _codex_text(p.get("content", ""))
        if t:
            text_parts.append(t)
        if tools:
            tool_parts.append(tools)
        last_a_turn_id = p.get("turn_id") or last_user_turn_id

    if last_a_turn_id is None:
        return None, None, None, None, False

    had_prose = bool(text_parts)
    asst_text = "\n".join(text_parts) if had_prose else "\n".join(tool_parts)
    # Use `<turn_id>:user` / `<turn_id>:assistant` so both halves disambiguate
    # if two turns share an id (defensive — shouldn't happen).
    user_uuid = f"{last_user_turn_id}:user"
    asst_uuid = f"{last_a_turn_id}:assistant"
    return user_text, user_uuid, asst_text, asst_uuid, had_prose


def find_last_turn(msgs: list) -> tuple:
    last_user_idx = None
    user_text = None
    user_uuid = None
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        msg = m.get("message") or {}
        if m.get("type") == "user" or msg.get("role") == "user":
            txt = extract_text(msg.get("content", ""))
            if txt and not txt.lstrip().startswith("[tool_result"):
                user_text = txt
                user_uuid = m.get("uuid") or f"idx{i}"
                last_user_idx = i
                break
    if last_user_idx is None:
        return None, None, None, None, False

    text_parts = []
    tool_parts = []
    last_a_uuid = None
    for j in range(last_user_idx + 1, len(msgs)):
        m = msgs[j]
        msg = m.get("message") or {}
        if m.get("type") == "assistant" or msg.get("role") == "assistant":
            t_only, tools = _extract_assistant(msg.get("content", ""))
            if t_only:
                text_parts.append(t_only)
            if tools:
                tool_parts.append(tools)
            last_a_uuid = m.get("uuid") or f"idx{j}"

    if last_a_uuid is None:
        return None, None, None, None, False

    had_prose = bool(text_parts)
    asst_text = "\n".join(text_parts) if had_prose else "\n".join(tool_parts)
    return user_text, user_uuid, asst_text, last_a_uuid, had_prose


def _load_state(state_path) -> dict:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {}


def _save_state(state_path, d: dict) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(d))
    except Exception:
        pass


def persist_last_turn(
    transcript_path: str,
    session_id: str,
    cwd: str,
    require_prose: bool = False,
) -> str:
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    msgs = read_transcript(transcript_path)
    if _is_codex_transcript(transcript_path):
        user_text, user_uuid, asst_text, a_uuid, had_prose = find_last_turn_codex(msgs)
    else:
        user_text, user_uuid, asst_text, a_uuid, had_prose = find_last_turn(msgs)
    if not user_text or not asst_text or not user_uuid:
        return ""
    if require_prose and not had_prose:
        return ""

    user_text = user_text[:8000]
    asst_text = asst_text[:12000]

    data_dir = resolve_data_dir(cwd)
    state_path = paths_for(data_dir)["state_path"]

    mem = Memory(data_dir=data_dir)
    try:
        mem.ensure_session(session_id, cwd)
        turn_id, action = mem.upsert_turn(session_id, user_uuid, user_text, asst_text, cwd)
    finally:
        mem.close()

    if action in ("insert", "update"):
        try:
            from .summarizer import spawn_background

            spawn_background(str(data_dir), turn_id)
        except Exception:
            pass

    if action in ("insert", "update"):
        state = _load_state(state_path)
        state[session_id] = a_uuid
        _save_state(state_path, state)
    return action
