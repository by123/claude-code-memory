"""Stop hook — persist the last user/assistant turn from the transcript."""
import json
import os
import sys
import traceback

from ._log import log


def _main() -> int:
    if os.environ.get("LYNX_MEMORY_NO_HOOK"):
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    session_id = data.get("session_id") or "unknown"
    cwd = data.get("cwd") or ""
    transcript_path = data.get("transcript_path") or ""

    try:
        from ..transcript import persist_last_turn
        persist_last_turn(transcript_path, session_id, cwd, require_prose=True)
    except Exception as e:
        log(f"[on_stop] ERROR: {e}\n{traceback.format_exc()}")
    return 0


def main() -> None:
    sys.exit(_main())


if __name__ == "__main__":
    main()
