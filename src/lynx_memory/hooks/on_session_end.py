"""Session-summary hook.

Claude Code: registered as `SessionEnd` — `session_id` in stdin is the session
that just ended; we summarize it.

Codex CLI: registered as `SessionStart` — `session_id` is the *new* session
about to begin (Codex has no SessionEnd event). We instead summarize the most
recent unsummarized session in the DB.
"""
import json
import os
import shutil
import subprocess
import sys
import traceback

from ._log import log


def _parse_target() -> str:
    for a in sys.argv[1:]:
        if a.startswith("--target="):
            return a.split("=", 1)[1]
    if "--target" in sys.argv:
        i = sys.argv.index("--target")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return os.environ.get("LYNX_MEMORY_TARGET", "claude_code")

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


def _model() -> str:
    return os.environ.get("LYNX_MEMORY_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)


def _summarize_via_cli(conversation: str) -> str:
    """Reuse the user's `claude` CLI session — no API key needed."""
    cli = shutil.which("claude")
    if cli is None:
        return ""
    env = os.environ.copy()
    env["LYNX_MEMORY_NO_HOOK"] = "1"
    try:
        proc = subprocess.run(
            [cli, "-p", "--model", _model(), "--output-format", "text",
             "--no-session-persistence",
             SUMMARIZE_PROMPT.format(conversation=conversation)],
            input="", capture_output=True, text=True,
            timeout=int(os.environ.get("SUMMARY_TIMEOUT", "60")),
            env=env,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _summarize_via_sdk(conversation: str) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=_model(),
            max_tokens=800,
            messages=[{"role": "user", "content": SUMMARIZE_PROMPT.format(conversation=conversation)}],
        )
    except Exception:
        return ""
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _summarize(conversation: str) -> str:
    """Try CLI first, then SDK. Return empty string on failure (caller skips)."""
    out = _summarize_via_cli(conversation)
    if out:
        return out
    return _summarize_via_sdk(conversation)


def _main() -> int:
    if os.environ.get("LYNX_MEMORY_NO_HOOK"):
        return 0
    target = _parse_target()
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    incoming_session_id = data.get("session_id") or ""
    cwd = data.get("cwd") or ""

    try:
        from ..config import load_env, resolve_data_dir
        from ..storage import Memory
        data_dir = resolve_data_dir(cwd)
        load_env(data_dir)

        mem = Memory(data_dir=data_dir)

        # Codex fires SessionStart for the *new* session — summarize the
        # previous one instead.
        if target == "codex":
            session_id = mem.find_unsummarized_session(
                exclude_session_id=incoming_session_id, min_turns=2
            )
            if not session_id:
                mem.close()
                return 0
        else:
            session_id = incoming_session_id
            if not session_id:
                mem.close()
                return 0

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
