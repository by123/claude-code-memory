"""UserPromptSubmit hook — inject top-K relevant memories into context.

Claude Code passes hook input on stdin as JSON. Anything we print to stdout
is injected as additional context for Claude. We fail silently on any error.
"""
import json
import os
import sys
import traceback

from ._log import log


def _main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = (data.get("prompt") or "").strip()
    session_id = data.get("session_id") or "unknown"
    cwd = data.get("cwd") or ""
    transcript_path = data.get("transcript_path") or ""

    # Persist the previous turn first — Stop hook often fires before the
    # assistant's final text is flushed to the transcript.
    try:
        from ..transcript import persist_last_turn
        persist_last_turn(transcript_path, session_id, cwd, require_prose=False)
    except Exception as e:
        log(f"[on_prompt] persist ERROR: {e}\n{traceback.format_exc()}")

    if not prompt or len(prompt) < 4:
        return 0

    try:
        from ..config import load_env, resolve_data_dir
        from ..storage import search_scoped
        load_env(resolve_data_dir(cwd))

        top_k = int(os.environ.get("TOP_K", 5))
        min_score = float(os.environ.get("MIN_SCORE", 0.3))
        scope = os.environ.get("CLAUDE_MEMORY_SCOPE", "auto")
        results = search_scoped(
            prompt, cwd=cwd, scope=scope, top_k=top_k, min_score=min_score
        )
    except Exception as e:
        log(f"[on_prompt] ERROR: {e}\n{traceback.format_exc()}")
        return 0

    if not results:
        return 0

    lines = ["<memory>", "Relevant context from prior conversations (auto-retrieved):"]
    for r in results:
        score = f"{r['score']:.2f}"
        kind = r["kind"]
        sc = r.get("scope", "")
        tag = f"{kind}" + (f" · {sc}" if sc else "")
        text = r["text"]
        if len(text) > 800:
            text = text[:800] + "…"
        lines.append(f"\n[{tag} · score={score}]\n{text}")
    lines.append("</memory>")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main() -> None:
    sys.exit(_main())


if __name__ == "__main__":
    main()
