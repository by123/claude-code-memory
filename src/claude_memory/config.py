"""Centralized paths and environment loading for claude-memory."""
import os
from pathlib import Path

from dotenv import load_dotenv

DATA_DIR = Path(
    os.environ.get(
        "CLAUDE_MEMORY_DIR",
        os.path.expanduser("~/.claude/claude-memory"),
    )
)
ENV_FILE = DATA_DIR / ".env"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "memory.db"
CHROMA_DIR = DB_DIR / "chroma"
LOG_PATH = DB_DIR / "hook.log"
STATE_PATH = DB_DIR / "last_turn.json"

CLAUDE_SETTINGS_PATH = Path(os.path.expanduser("~/.claude/settings.json"))


def load_env() -> None:
    """Load DATA_DIR/.env into os.environ if present (idempotent)."""
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
