"""UserPromptSubmit hook — inject top-K relevant memories into context.

Claude Code and Codex CLI both pass hook input on stdin as JSON, with the
exact same field names (session_id, cwd, transcript_path, prompt). They
differ in how to inject context:

  - Claude Code accepts plain stdout text (it gets appended to the prompt).
  - Codex CLI requires a JSON envelope:
      {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                              "additionalContext": "<text>"}}

We pick the format from `--target {claude_code,codex}` (default claude_code).
We fail silently on any error.
"""
import json
import os
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


def _main() -> int:
    if os.environ.get("LYNX_MEMORY_NO_HOOK"):
        return 0
    target = _parse_target()
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
        min_score = float(os.environ.get("MIN_SCORE", 0.7))
        scope = os.environ.get("LYNX_MEMORY_SCOPE", "auto")
        results = search_scoped(
            prompt, cwd=cwd, scope=scope, top_k=top_k, min_score=min_score
        )
    except Exception as e:
        log(f"[on_prompt] ERROR: {e}\n{traceback.format_exc()}")
        return 0

    if not results:
        return 0

    try:
        from ..config import GLOBAL_DATA_DIR, find_project_root
        from ..storage import Memory

        proj_dir = find_project_root(cwd) if cwd else None
        any_project_hit = any(r.get("scope") == "project" for r in results)
        target_dir = proj_dir if (proj_dir is not None and any_project_hit) else GLOBAL_DATA_DIR
        scope_used = "project" if target_dir == proj_dir else "global"

        m = Memory(data_dir=target_dir)
        try:
            m.record_retrieval(
                prompt=prompt,
                hits=results,
                session_id=session_id,
                cwd=cwd,
                scope_used=scope_used,
            )
        finally:
            m.close()
    except Exception as e:
        log(f"[on_prompt] record_retrieval ERROR: {e}\n{traceback.format_exc()}")

    lines = ["<memory>", "Relevant context from prior conversations (auto-retrieved):"]
    for r in results:
        score = f"{r['score']:.2f}"
        kind = r["kind"]
        sc = r.get("scope", "")
        summary = r.get("summary")
        if summary:
            tag = f"{kind}" + (f" · {sc}" if sc else "") + " · summary"
            text = summary
        else:
            tag = f"{kind}" + (f" · {sc}" if sc else "")
            text = r["text"]
        if len(text) > 1200:
            text = text[:1200] + "…"
        lines.append(f"\n[{tag} · score={score}]\n{text}")
    lines.append("</memory>")
    body = "\n".join(lines)

    if target == "codex":
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": body,
            }
        }))
    else:
        sys.stdout.write(body + "\n")
    return 0


def main() -> None:
    sys.exit(_main())


if __name__ == "__main__":
    main()
