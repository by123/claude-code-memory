"""SessionEnd hook — summarize the session with Claude Haiku and store it."""
import json
import os
import sys
import traceback

from ._log import log

SUMMARIZE_PROMPT = """You are summarizing a conversation between a user and Claude Code for a long-term memory system.

Produce a concise summary (under 250 words) capturing:
- What the user was working on and the final outcome
- Key decisions made and the reasoning behind them
- Facts about the user, their project, or their environment worth remembering
- Open questions or follow-ups

Write in third person, plain prose, no headers. Be specific with names/paths/tools.

Conversation:
{conversation}"""

DEFAULT_SUMMARY_MODEL = "claude-haiku-4-5-20251001"


def _summarize(conversation: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    model = os.environ.get("CLAUDE_MEMORY_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)
    resp = client.messages.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": SUMMARIZE_PROMPT.format(conversation=conversation)}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _main() -> int:
    if os.environ.get("CLAUDE_MEMORY_NO_HOOK"):
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    session_id = data.get("session_id") or ""
    if not session_id:
        return 0
    cwd = data.get("cwd") or ""

    try:
        from ..config import load_env, resolve_data_dir
        from ..storage import Memory
        data_dir = resolve_data_dir(cwd)
        load_env(data_dir)

        mem = Memory(data_dir=data_dir)
        turns = mem.get_session_turns(session_id)
        if len(turns) < 2:
            mem.end_session(session_id)
            mem.close()
            return 0

        parts = []
        for t in turns:
            u = (t["user_msg"] or "").strip()[:2000]
            a = (t["assistant_msg"] or "").strip()[:2000]
            parts.append(f"USER: {u}\nASSISTANT: {a}")
        conversation = "\n\n---\n\n".join(parts)
        if len(conversation) > 60000:
            conversation = conversation[:60000] + "\n\n[...truncated]"

        summary = _summarize(conversation)
        if summary:
            mem.add_summary(session_id, summary, len(turns))

        mem.end_session(session_id)
        mem.close()
    except Exception as e:
        log(f"[on_session_end] ERROR: {e}\n{traceback.format_exc()}")
        return 0
    return 0


def main() -> None:
    sys.exit(_main())


if __name__ == "__main__":
    main()
