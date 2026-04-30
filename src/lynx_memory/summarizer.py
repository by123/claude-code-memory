"""Turn summarizer.

Generates a compact summary for a single (user, assistant) turn so memory
recall can inject summaries into context instead of full prose.

Three backends:
  1. CLI (claude, default): shell out to `claude -p --model <haiku>` and reuse the
     user's already-authenticated Claude Code session. No extra API key needed.
     We set LYNX_MEMORY_NO_HOOK=1 in the child so that our own hooks no-op.
  2. CLI (codex, fallback): if `claude` CLI is missing but `codex` is available,
     shell out to `codex exec --ephemeral`. Caveats:
       - codex has no `--append-system-prompt`; the system instructions are
         prepended to the user prompt body instead.
       - codex routes to whatever provider/model is configured in
         `~/.codex/config.toml`. SUMMARY_MODEL is IGNORED on this path — to
         summarize with a specific model via codex, configure a codex profile.
       - The summary is attributed as source="codex" with model=None, since
         we cannot reliably know which provider codex picked.
  3. SDK fallback: if both CLI tools are missing AND ANTHROPIC_API_KEY is set,
     fall back to the Anthropic SDK with prompt caching.

Defaults:
  - SUMMARY_ENABLED=1 (set "0"/"false" to disable)
  - SUMMARY_MODEL=claude-haiku-4-5-20251001  (claude CLI / SDK only)
  - SUMMARY_BACKEND=auto | cli | sdk
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

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


def _codex_cli() -> Optional[str]:
    return shutil.which("codex")


SummaryResult = Tuple[str, str, Optional[str]]  # (summary, source, model)


def _conversation_body(user_msg: str, assistant_msg: str) -> str:
    return f"User:\n{user_msg[:6000]}\n\n---\n\nAssistant:\n{assistant_msg[:10000]}"


def _run_cli(
    argv: list,
    *,
    source: str,
    model: Optional[str],
    output_file: Optional[str] = None,
) -> Optional[SummaryResult]:
    """Shell out to a CLI summarizer; collect stdout (or output_file) as text.

    `output_file`, when given, is preferred over stdout (codex writes its
    final message there, avoiding session-banner noise).
    """
    env = os.environ.copy()
    env["LYNX_MEMORY_NO_HOOK"] = "1"
    try:
        proc = subprocess.run(
            argv,
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
    if output_file is not None:
        try:
            text = Path(output_file).read_text(encoding="utf-8").strip()
        except Exception:
            return None
    else:
        text = (proc.stdout or "").strip()
    return (text, source, model) if text else None


def _summarize_via_codex(user_msg: str, assistant_msg: str) -> Optional[SummaryResult]:
    """Fallback when claude CLI is unavailable.

    codex has no `--append-system-prompt`; we prepend _SYSTEM into the body.
    We also do not pass --model: codex uses whatever is configured in
    ~/.codex/config.toml. SUMMARY_MODEL is intentionally not forwarded, and
    the result is attributed source="codex" with model=None.
    """
    cli = _codex_cli()
    if cli is None:
        return None
    content = (
        f"{_SYSTEM}\n\n"
        "下面是需要摘要的对话。请严格按上面的格式输出摘要正文：\n\n"
        + _conversation_body(user_msg, assistant_msg)
    )
    out_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, prefix="lynx-codex-"
        ) as f:
            out_path = f.name
        return _run_cli(
            [
                cli, "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--color", "never",
                "--output-last-message", out_path,
                content,
            ],
            source="codex",
            model=None,
            output_file=out_path,
        )
    finally:
        if out_path:
            try:
                os.unlink(out_path)
            except OSError:
                pass


def _summarize_via_cli(user_msg: str, assistant_msg: str) -> Optional[SummaryResult]:
    """Primary backend: shell out to `claude` CLI."""
    cli = _claude_cli()
    if cli is None:
        return None
    content = (
        "下面是需要摘要的对话。请严格按系统提示中的格式输出摘要正文：\n\n"
        + _conversation_body(user_msg, assistant_msg)
    )
    model = model_name()
    return _run_cli(
        [
            cli, "-p",
            "--model", model,
            "--append-system-prompt", _SYSTEM,
            "--output-format", "text",
            "--no-session-persistence",
            content,
        ],
        source="haiku",
        model=model,
    )


@lru_cache(maxsize=1)
def _sdk_client():
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


def _summarize_via_sdk(user_msg: str, assistant_msg: str) -> Optional[SummaryResult]:
    try:
        client = _sdk_client()
    except Exception:
        return None
    content = f"User:\n{user_msg[:6000]}\n\n---\n\nAssistant:\n{assistant_msg[:10000]}"
    model = model_name()
    try:
        resp = client.messages.create(
            model=model,
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
    return (text, "haiku", model) if text else None


def summarize_with_source(user_msg: str, assistant_msg: str) -> Optional[SummaryResult]:
    """Return (summary, source, model), or None on failure / if disabled.

    `model` may be None when the backend (codex CLI) does not expose which
    model it routed to.
    """
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
    # auto: try claude CLI first, then codex CLI, finally SDK
    if _claude_cli() is not None:
        out = _summarize_via_cli(user_msg, assistant_msg)
        if out:
            return out
    if _codex_cli() is not None:
        out = _summarize_via_codex(user_msg, assistant_msg)
        if out:
            return out
    return _summarize_via_sdk(user_msg, assistant_msg)


def summarize(user_msg: str, assistant_msg: str) -> Optional[str]:
    result = summarize_with_source(user_msg, assistant_msg)
    return result[0] if result else None


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
        result = summarize_with_source(t["user_msg"], t["assistant_msg"])
        if not result:
            return 2
        summary, source, used_model = result
        mem.set_summary(turn_id, summary, source=source, model=used_model)
    finally:
        mem.close()
    return 0


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(64)
    sys.exit(_run_one(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
