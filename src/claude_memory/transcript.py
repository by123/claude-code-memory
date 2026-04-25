"""Shared transcript parsing + turn persistence for Stop / UserPromptSubmit hooks."""
import json
import os

from .config import STATE_PATH
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


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(d: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(d))
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
    user_text, user_uuid, asst_text, a_uuid, had_prose = find_last_turn(msgs)
    if not user_text or not asst_text or not user_uuid:
        return ""
    if require_prose and not had_prose:
        return ""

    user_text = user_text[:8000]
    asst_text = asst_text[:12000]

    mem = Memory()
    try:
        mem.ensure_session(session_id, cwd)
        _, action = mem.upsert_turn(session_id, user_uuid, user_text, asst_text, cwd)
    finally:
        mem.close()

    if action in ("insert", "update"):
        state = _load_state()
        state[session_id] = a_uuid
        _save_state(state)
    return action
