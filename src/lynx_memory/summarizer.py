"""Haiku-powered turn summarizer.

Generates a compact summary for a single (user, assistant) turn so memory
recall can inject summaries into context instead of full prose.

Two backends:
  1. CLI (default): shell out to `claude -p --model <haiku>` and reuse the
     user's already-authenticated Claude Code session. No extra API key
     needed. We set LYNX_MEMORY_NO_HOOK=1 in the child so that our own
     UserPromptSubmit/Stop hooks no-op inside the subprocess and we don't
     recurse.
  2. SDK fallback: if `claude` CLI is missing AND ANTHROPIC_API_KEY is set,
     fall back to the Anthropic SDK with prompt caching.

Defaults:
  - SUMMARY_ENABLED=1 (set "0"/"false" to disable)
  - SUMMARY_MODEL=claude-haiku-4-5-20251001
  - SUMMARY_BACKEND=auto | cli | sdk
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You compress one User+Assistant turn into a short summary. "
    "Write the summary in the SAME LANGUAGE as the original turn (do not translate).\n"
    "1) First line: one sentence stating the user's question and the final conclusion/action.\n"
    "2) Then 2-5 short bullet points preserving concrete details: file paths, function/variable names, "
    "commands, numeric thresholds, reasons for decisions.\n"
    "3) Do not repeat long sentences verbatim, no pleasantries, no extra headings; keep the total under "
    "~400 characters (or ~120 English words).\n"
    "Goal: future retrieval should be able to fully understand the facts and decisions of this turn from "
    "the summary alone.\n"
    "Output the summary body directly, with no surrounding explanation."
)


def is_enabled() -> bool:
    v = os.environ.get("SUMMARY_ENABLED", "1").strip().lower()
    return v not in ("0", "false", "off", "no", "")


def model_name() -> str:
    return os.environ.get("SUMMARY_MODEL", DEFAULT_MODEL)


def _backend() -> str:
    return os.environ.get("SUMMARY_BACKEND", "auto").strip().lower()


def _claude_cli() -> Optional[str]:
    return shutil.which("claude")


def _summarize_via_cli(user_msg: str, assistant_msg: str) -> Optional[str]:
    cli = _claude_cli()
    if cli is None:
        return None
    content = (
        "下面是需要摘要的对话。请严格按系统提示中的格式输出摘要正文：\n\n"
        f"User:\n{user_msg[:6000]}\n\n---\n\nAssistant:\n{assistant_msg[:10000]}"
    )
    env = os.environ.copy()
    env["LYNX_MEMORY_NO_HOOK"] = "1"
    try:
        proc = subprocess.run(
            [
                cli,
                "-p",
                "--model",
                model_name(),
                "--append-system-prompt",
                _SYSTEM,
                "--output-format",
                "text",
                "--no-session-persistence",
                content,
            ],
            input="",
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("SUMMARY_TIMEOUT", "60")),
            env=env,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


@lru_cache(maxsize=1)
def _sdk_client():
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


def _summarize_via_sdk(user_msg: str, assistant_msg: str) -> Optional[str]:
    try:
        client = _sdk_client()
    except Exception:
        return None
    content = f"User:\n{user_msg[:6000]}\n\n---\n\nAssistant:\n{assistant_msg[:10000]}"
    try:
        resp = client.messages.create(
            model=model_name(),
            max_tokens=600,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": content}],
        )
    except Exception:
        return None
    parts = []
    for block in resp.content or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    text = "\n".join(parts).strip()
    return text or None


def summarize(user_msg: str, assistant_msg: str) -> Optional[str]:
    """Return a short summary, or None on failure / if disabled."""
    if not is_enabled():
        return None
    user_msg = (user_msg or "").strip()
    assistant_msg = (assistant_msg or "").strip()
    if not user_msg or not assistant_msg:
        return None

    backend = _backend()
    if backend == "cli":
        return _summarize_via_cli(user_msg, assistant_msg)
    if backend == "sdk":
        return _summarize_via_sdk(user_msg, assistant_msg)
    # auto: try CLI first, fall back to SDK if CLI missing
    if _claude_cli() is not None:
        out = _summarize_via_cli(user_msg, assistant_msg)
        if out:
            return out
    return _summarize_via_sdk(user_msg, assistant_msg)


def spawn_background(data_dir: str, turn_id: str) -> None:
    """Detach a child process to summarize a turn without blocking the hook."""
    if not is_enabled():
        return
    try:
        subprocess.Popen(
            [sys.executable, "-m", "lynx_memory.summarizer", data_dir, turn_id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        pass


def _run_one(data_dir: str, turn_id: str) -> int:
    from .config import load_env
    from .storage import Memory

    ddir = Path(data_dir)
    load_env(ddir)
    mem = Memory(data_dir=ddir)
    try:
        t = mem.get_turn(turn_id)
        if t is None:
            return 1
        if t.get("summary"):
            return 0  # already summarized
        s = summarize(t["user_msg"], t["assistant_msg"])
        if not s:
            return 2
        mem.set_summary(turn_id, s, model=model_name())
    finally:
        mem.close()
    return 0


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(64)
    sys.exit(_run_one(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
