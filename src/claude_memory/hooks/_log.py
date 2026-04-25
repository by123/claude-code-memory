"""Shared file logger for hooks (silent on any error)."""
from ..config import LOG_PATH


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(msg + "\n")
    except Exception:
        pass
