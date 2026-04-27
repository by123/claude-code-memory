"""claude-memory CLI: init, uninstall, status, doctor, merge."""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from importlib import resources
from pathlib import Path

from . import __version__
from .config import (
    CLAUDE_SETTINGS_PATH,
    DATA_DIR,
    DB_PATH,
    ENV_FILE,
    GLOBAL_DATA_DIR,
    LOG_PATH,
    PROJECT_MARKER,
    ensure_dirs,
    find_project_root,
    load_env,
    paths_for,
    resolve_data_dir,
)

CLAUDE_COMMANDS_DIR = Path(os.path.expanduser("~/.claude/commands"))
SLASH_COMMAND_NAMES = (
    "claude-memory-status.md",
    "claude-memory-pull-global.md",
    "claude-memory-push-global.md",
    "claude-memory-delete.md",
    "claude-memory-history.md",
)

HOOK_COMMANDS = {
    "UserPromptSubmit": ("claude-memory-on-prompt", 10000),
    "Stop": ("claude-memory-on-stop", 15000),
    "SessionEnd": ("claude-memory-on-session-end", 60000),
}

HOOK_MARKER_COMMANDS = {cmd for cmd, _ in HOOK_COMMANDS.values()}


# --------------------------------------------------------------------- helpers

def _print_ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _print_warn(msg: str) -> None:
    print(f"  ! {msg}")


def _print_err(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def _read_settings() -> dict:
    if not CLAUDE_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(CLAUDE_SETTINGS_PATH.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Failed to parse {CLAUDE_SETTINGS_PATH}: {e}\n"
            "Please fix the JSON manually before running this command."
        )


def _backup_settings() -> Path | None:
    if not CLAUDE_SETTINGS_PATH.exists():
        return None
    bak = CLAUDE_SETTINGS_PATH.with_suffix(f".json.bak.{int(time.time())}")
    shutil.copy2(CLAUDE_SETTINGS_PATH, bak)
    return bak


def _write_settings(settings: dict) -> None:
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")


def _hook_block_has_command(block: dict, command: str) -> bool:
    for h in block.get("hooks", []) or []:
        if h.get("type") == "command" and h.get("command") == command:
            return True
    return False


def _ensure_hook(settings: dict, event: str, command: str, timeout: int) -> bool:
    """Insert our hook command for `event` if not already present.

    Returns True if a change was made, False if already present.
    """
    hooks = settings.setdefault("hooks", {})
    blocks = hooks.setdefault(event, [])

    for block in blocks:
        if _hook_block_has_command(block, command):
            return False

    blocks.append(
        {
            "hooks": [
                {"type": "command", "command": command, "timeout": timeout}
            ]
        }
    )
    return True


def _remove_hook(settings: dict, event: str, command: str) -> bool:
    hooks = settings.get("hooks", {})
    blocks = hooks.get(event)
    if not blocks:
        return False
    new_blocks = []
    changed = False
    for block in blocks:
        inner = block.get("hooks", []) or []
        kept = [h for h in inner if not (h.get("type") == "command" and h.get("command") == command)]
        if len(kept) != len(inner):
            changed = True
        if kept:
            new_blocks.append({**block, "hooks": kept})
    if changed:
        if new_blocks:
            hooks[event] = new_blocks
        else:
            hooks.pop(event, None)
    if hooks == {}:
        settings.pop("hooks", None)
    return changed


def _ensure_env_file() -> bool:
    """Make sure ENV_FILE exists with at least a VOYAGE_API_KEY line.

    If the file is missing or has no VOYAGE_API_KEY, prompt the user.
    Returns True if it now contains a non-empty key.
    """
    ensure_dirs()
    existing = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    if not existing.get("VOYAGE_API_KEY"):
        try:
            key = input(
                "Enter your VOYAGE_API_KEY (get one at https://www.voyageai.com/): "
            ).strip()
        except EOFError:
            key = ""
        if not key:
            _print_warn(
                "VOYAGE_API_KEY not provided. Hooks will fail until you set it in "
                f"{ENV_FILE}"
            )
            existing.setdefault("VOYAGE_API_KEY", "")
        else:
            existing["VOYAGE_API_KEY"] = key

    existing.setdefault("TOP_K", "5")
    existing.setdefault("MIN_SCORE", "0.7")
    existing.setdefault("SUMMARY_ENABLED", "1")
    existing.setdefault("SUMMARY_MODEL", "claude-haiku-4-5-20251001")
    existing.setdefault("SUMMARY_BACKEND", "auto")

    lines = [f"{k}={v}" for k, v in existing.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass
    return bool(existing.get("VOYAGE_API_KEY"))


# --------------------------------------------------------------------- commands

def cmd_init(args: argparse.Namespace) -> int:
    print(f"claude-memory v{__version__} — installing")
    print(f"  data dir: {DATA_DIR}")
    print(f"  settings: {CLAUDE_SETTINGS_PATH}")
    print()

    ensure_dirs()
    _print_ok(f"Created {DATA_DIR}")

    has_key = _ensure_env_file()
    if has_key:
        _print_ok(f"Wrote {ENV_FILE}")
    else:
        _print_warn(f"Wrote {ENV_FILE} (VOYAGE_API_KEY still empty)")

    settings = _read_settings()
    bak = _backup_settings()
    if bak:
        _print_ok(f"Backed up settings.json → {bak.name}")

    changed = False
    for event, (command, timeout) in HOOK_COMMANDS.items():
        if _ensure_hook(settings, event, command, timeout):
            _print_ok(f"Registered hook: {event} → {command}")
            changed = True
        else:
            _print_ok(f"Hook already registered: {event}")

    if changed:
        _write_settings(settings)
        _print_ok(f"Updated {CLAUDE_SETTINGS_PATH}")

    for name in SLASH_COMMAND_NAMES:
        if _install_slash_command(name):
            _print_ok(f"Installed slash command: /{name[:-3]} → {CLAUDE_COMMANDS_DIR / name}")
        else:
            _print_ok(f"Slash command already up to date: /{name[:-3]}")

    print()
    print("Done. Open a new Claude Code session and chat for a few turns.")
    print("Verify with:  claude-memory status")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    print("claude-memory — removing hooks from settings.json")

    if not CLAUDE_SETTINGS_PATH.exists():
        _print_warn(f"{CLAUDE_SETTINGS_PATH} does not exist; nothing to do.")
        return 0

    settings = _read_settings()
    bak = _backup_settings()
    if bak:
        _print_ok(f"Backed up settings.json → {bak.name}")

    any_removed = False
    for event, (command, _) in HOOK_COMMANDS.items():
        if _remove_hook(settings, event, command):
            _print_ok(f"Removed hook: {event} → {command}")
            any_removed = True

    if any_removed:
        _write_settings(settings)
        _print_ok(f"Updated {CLAUDE_SETTINGS_PATH}")
    else:
        _print_warn("No claude-memory hooks were present in settings.json.")

    for name in SLASH_COMMAND_NAMES:
        if _remove_slash_command(name):
            _print_ok(f"Removed slash command: {CLAUDE_COMMANDS_DIR / name}")

    print()
    print(f"Your memory data is preserved at: {DATA_DIR}")
    print("Delete it manually if you want a clean slate:")
    print(f"  rm -rf {DATA_DIR}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(f"claude-memory v{__version__}")
    cwd = Path.cwd()
    proj = find_project_root(cwd)
    active = resolve_data_dir(cwd)
    active_paths = paths_for(active)
    scope = "project" if proj else "global"

    print(f"  cwd            : {cwd}")
    print(f"  scope          : {scope}  (active dir: {active})")
    if proj:
        print(f"  project marker : {proj}")
    print(f"  global data    : {DATA_DIR}  (exists={DATA_DIR.exists()})")
    print(f"  env file       : {ENV_FILE}  (exists={ENV_FILE.exists()})")
    print(f"  database       : {active_paths['db_path']}  (exists={active_paths['db_path'].exists()})")
    print(f"  hook log       : {LOG_PATH}")
    print(f"  settings.json  : {CLAUDE_SETTINGS_PATH}  (exists={CLAUDE_SETTINGS_PATH.exists()})")

    load_env()
    have_key = bool(os.environ.get("VOYAGE_API_KEY"))
    print(f"  VOYAGE_API_KEY : {'set' if have_key else 'MISSING'}")

    if CLAUDE_SETTINGS_PATH.exists():
        try:
            settings = _read_settings()
        except SystemExit as e:
            _print_err(str(e))
            return 1
        print("  hooks:")
        for event, (command, _) in HOOK_COMMANDS.items():
            blocks = settings.get("hooks", {}).get(event, [])
            present = any(_hook_block_has_command(b, command) for b in blocks)
            print(f"    {event:<18} {'✓' if present else '✗'}  {command}")

    if active_paths["db_path"].exists() and have_key:
        try:
            from .storage import Memory
            mem = Memory(data_dir=active)
            try:
                stats = mem.stats()
            finally:
                mem.close()
            print(f"  stats ({scope}):")
            for k, v in stats.items():
                print(f"    {k:<20} {v}")
        except Exception as e:
            _print_warn(f"Could not read stats: {e}")
    return 0


def cmd_init_project(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve() if args.path else Path.cwd()
    if not target.exists():
        _print_err(f"Path does not exist: {target}")
        return 1
    if not target.is_dir():
        _print_err(f"Path is not a directory: {target}")
        return 1

    marker = target / PROJECT_MARKER
    if marker.exists():
        _print_warn(f"Project store already initialised at {marker}")
    else:
        marker.mkdir(parents=True)
        _print_ok(f"Created {marker}")

    (marker / "db").mkdir(parents=True, exist_ok=True)

    gitignore = marker / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n")
        _print_ok(f"Wrote {gitignore} (project memory is git-ignored by default)")

    print()
    print(f"Project memory will live in: {marker}")
    print("Run inside this directory:  claude-memory status")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print("claude-memory doctor")
    rc = 0

    print(f"  python         : {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        _print_err("Python 3.10+ required.")
        rc = 1
    else:
        _print_ok("Python version OK.")

    for mod in ("chromadb", "voyageai", "mcp", "anthropic", "dotenv"):
        try:
            __import__(mod)
            _print_ok(f"import {mod}")
        except Exception as e:
            _print_err(f"import {mod} failed: {e}")
            rc = 1

    ensure_dirs()
    test = DATA_DIR / ".write_test"
    try:
        test.write_text("ok")
        test.unlink()
        _print_ok(f"Data dir writable: {DATA_DIR}")
    except Exception as e:
        _print_err(f"Data dir not writable: {e}")
        rc = 1

    load_env()
    if not os.environ.get("VOYAGE_API_KEY"):
        _print_err("VOYAGE_API_KEY is not set (run `claude-memory init`).")
        rc = 1
    else:
        try:
            from .embeddings import embed_one
            v = embed_one("hello world", input_type="query")
            if isinstance(v, list) and len(v) > 0:
                _print_ok(f"Voyage API call OK (embedding dim={len(v)}).")
            else:
                _print_err("Voyage API returned an empty embedding.")
                rc = 1
        except Exception as e:
            _print_err(f"Voyage API call failed: {e}")
            rc = 1

    if CLAUDE_SETTINGS_PATH.exists():
        try:
            _read_settings()
            _print_ok(f"settings.json is valid JSON.")
        except SystemExit as e:
            _print_err(str(e))
            rc = 1
    else:
        _print_warn(f"settings.json does not exist yet (run `claude-memory init`).")

    return rc


# --------------------------------------------------------------------- slash command

def _read_bundled_command(name: str) -> str:
    """Read a bundled slash-command markdown file shipped inside the package."""
    return (
        resources.files("claude_memory.assets.commands")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def _install_slash_command(name: str) -> bool:
    """Copy a bundled slash command into ~/.claude/commands/.

    Returns True if a write happened, False if the existing file already matches.
    """
    src = _read_bundled_command(name)
    CLAUDE_COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    dst = CLAUDE_COMMANDS_DIR / name
    if dst.exists() and dst.read_text(encoding="utf-8") == src:
        return False
    if dst.exists():
        bak = dst.with_suffix(f".md.bak.{int(time.time())}")
        shutil.copy2(dst, bak)
    dst.write_text(src, encoding="utf-8")
    return True


def _remove_slash_command(name: str) -> bool:
    dst = CLAUDE_COMMANDS_DIR / name
    if not dst.exists():
        return False
    try:
        if dst.read_text(encoding="utf-8") != _read_bundled_command(name):
            _print_warn(
                f"{dst} differs from the bundled version; left it alone. "
                "Delete it manually if you want it gone."
            )
            return False
    except Exception:
        return False
    dst.unlink()
    return True


# --------------------------------------------------------------------- merge

def _resolve_scope_dir(name: str, cwd: Path) -> Path | None:
    """Map 'project'/'global' to a concrete data dir for the given cwd."""
    if name == "global":
        return GLOBAL_DATA_DIR
    if name == "project":
        return find_project_root(cwd)
    raise ValueError(f"Unknown scope: {name!r}")


def _copy_sqlite_rows(src_db: Path, dst_db: Path) -> dict:
    """Copy sessions/turns/summaries from src to dst, ignoring id collisions."""
    counts = {"sessions": 0, "turns": 0, "summaries": 0}
    if not src_db.exists():
        return counts
    s = sqlite3.connect(src_db)
    s.row_factory = sqlite3.Row
    d = sqlite3.connect(dst_db)
    try:
        for table in ("sessions", "turns", "summaries"):
            try:
                rows = s.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                continue
            for row in rows:
                cols = row.keys()
                placeholders = ",".join("?" for _ in cols)
                col_list = ",".join(cols)
                cur = d.execute(
                    f"INSERT OR IGNORE INTO {table}({col_list}) VALUES({placeholders})",
                    tuple(row[c] for c in cols),
                )
                counts[table] += cur.rowcount
        d.commit()
    finally:
        s.close()
        d.close()
    return counts


def _copy_chroma(src_dir: Path, dst_dir: Path) -> dict:
    """Copy embeddings + docs from src chroma to dst chroma using upsert."""
    import chromadb
    from chromadb.config import Settings

    counts = {"turns": 0, "summaries": 0}
    src = chromadb.PersistentClient(path=str(src_dir), settings=Settings(anonymized_telemetry=False))
    dst = chromadb.PersistentClient(path=str(dst_dir), settings=Settings(anonymized_telemetry=False))

    for name in ("turns", "summaries"):
        try:
            src_col = src.get_collection(name)
        except Exception:
            continue
        dst_col = dst.get_or_create_collection(name, embedding_function=None, metadata={"hnsw:space": "cosine"})
        n = src_col.count()
        if n == 0:
            continue
        data = src_col.get(include=["embeddings", "documents", "metadatas"], limit=n)
        ids = data.get("ids") or []
        if not ids:
            continue
        dst_col.upsert(
            ids=ids,
            embeddings=data.get("embeddings"),
            documents=data.get("documents"),
            metadatas=data.get("metadatas"),
        )
        counts[name] = len(ids)
    return counts


def cmd_merge(args: argparse.Namespace) -> int:
    if args.from_ == args.to:
        _print_err("`--from` and `--to` must differ.")
        return 1

    cwd = Path.cwd()
    src_dir = _resolve_scope_dir(args.from_, cwd)
    dst_dir = _resolve_scope_dir(args.to, cwd)

    if src_dir is None:
        _print_err(f"Source scope '{args.from_}' not found (no project marker walking up from {cwd}).")
        return 1
    if dst_dir is None:
        # Target = project but no marker yet: create one in cwd.
        marker = cwd / PROJECT_MARKER
        marker.mkdir(parents=True, exist_ok=True)
        (marker / "db").mkdir(parents=True, exist_ok=True)
        dst_dir = marker
        _print_ok(f"Created project store at {marker}")

    src_paths = paths_for(src_dir)
    dst_paths = paths_for(dst_dir)

    print(f"claude-memory merge  {args.from_} → {args.to}")
    print(f"  source : {src_dir}")
    print(f"  target : {dst_dir}")

    if not src_paths["db_path"].exists():
        _print_warn(f"Source has no database yet ({src_paths['db_path']}); nothing to merge.")
        return 0

    if args.dry_run:
        s = sqlite3.connect(src_paths["db_path"])
        try:
            for t in ("sessions", "turns", "summaries"):
                try:
                    n = s.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    print(f"  would copy {n} rows from {t}")
                except sqlite3.OperationalError:
                    pass
        finally:
            s.close()
        return 0

    # Touch target schema by opening a Memory once (creates tables + chroma dirs).
    from .storage import Memory
    m = Memory(data_dir=dst_dir)
    m.close()

    sql_counts = _copy_sqlite_rows(src_paths["db_path"], dst_paths["db_path"])
    _print_ok(
        f"SQLite copied: sessions={sql_counts['sessions']}, "
        f"turns={sql_counts['turns']}, summaries={sql_counts['summaries']}"
    )

    try:
        ch_counts = _copy_chroma(src_paths["chroma_dir"], dst_paths["chroma_dir"])
        _print_ok(f"Chroma copied: turns={ch_counts['turns']}, summaries={ch_counts['summaries']}")
    except Exception as e:
        _print_err(f"Chroma copy failed: {e}")
        return 1

    if args.delete_source:
        if not args.yes:
            try:
                ans = input(f"Delete source store at {src_dir}? [y/N] ").strip().lower()
            except EOFError:
                ans = ""
            if ans != "y":
                _print_warn("Skipped --delete-source (not confirmed).")
                return 0
        for sub in ("db",):
            p = src_dir / sub
            if p.exists():
                shutil.rmtree(p)
        _print_ok(f"Cleared source data dirs under {src_dir}")

    return 0


# --------------------------------------------------------------------- delete

def cmd_delete(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    scopes: list[tuple[str, Path | None]] = []
    if args.scope in ("project", "both"):
        scopes.append(("project", _resolve_scope_dir("project", cwd)))
    if args.scope in ("global", "both"):
        scopes.append(("global", GLOBAL_DATA_DIR))

    targets: list[tuple[str, Path]] = []
    for label, d in scopes:
        if d is None:
            _print_warn(f"{label}: no project marker found walking up from {cwd}; skipping.")
            continue
        if not (d / "db").exists():
            _print_warn(f"{label}: nothing to delete at {d}/db.")
            continue
        targets.append((label, d))

    if not targets:
        _print_warn("Nothing to delete.")
        return 0

    print("claude-memory delete — the following data will be permanently removed:")
    for label, d in targets:
        print(f"  - {label}: {d}/db  (sqlite + chroma)")

    if not args.yes:
        try:
            ans1 = input("Type the word DELETE to confirm: ").strip()
        except EOFError:
            ans1 = ""
        if ans1 != "DELETE":
            _print_warn("Aborted (confirmation phrase not entered).")
            return 1
        try:
            ans2 = input("Are you absolutely sure? [y/N] ").strip().lower()
        except EOFError:
            ans2 = ""
        if ans2 != "y":
            _print_warn("Aborted (second confirmation declined).")
            return 1

    for label, d in targets:
        db_dir = d / "db"
        if db_dir.exists():
            shutil.rmtree(db_dir)
            _print_ok(f"{label}: removed {db_dir}")
    return 0


# --------------------------------------------------------------------- web

def cmd_web(args: argparse.Namespace) -> int:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        _print_err(
            "uvicorn is not installed. Reinstall with `pip install -U claude-code-memory`."
        )
        return 1

    host = args.host
    port = args.port
    if port == 0:
        # Pre-bind to grab a free port so we can print/open it before uvicorn starts.
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            port = s.getsockname()[1]

    url = f"http://{host}:{port}"
    print(f"claude-memory web — serving at {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        import threading
        import webbrowser

        def _open_later() -> None:
            import time as _t
            _t.sleep(0.6)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open_later, daemon=True).start()

    import uvicorn
    uvicorn.run("claude_memory.web:app", host=host, port=port, log_level="warning")
    return 0


# --------------------------------------------------------------------- entrypoint

def main() -> None:
    p = argparse.ArgumentParser(
        prog="claude-memory",
        description="Persistent semantic memory for Claude Code.",
    )
    p.add_argument("--version", action="version", version=f"claude-memory {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="Install hooks into ~/.claude/settings.json")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("uninstall", help="Remove hooks from ~/.claude/settings.json")
    sp.set_defaults(func=cmd_uninstall)

    sp = sub.add_parser(
        "init-project",
        help="Create a project-scoped memory store (.claude-memory/) in this directory",
    )
    sp.add_argument("path", nargs="?", default=None, help="Project root (default: cwd)")
    sp.set_defaults(func=cmd_init_project)

    sp = sub.add_parser("status", help="Show installation status and stats")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("doctor", help="Check environment and Voyage API key")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser(
        "merge",
        help="Merge memory between project and global stores",
    )
    sp.add_argument("--from", dest="from_", required=True, choices=["project", "global"])
    sp.add_argument("--to", required=True, choices=["project", "global"])
    sp.add_argument("--dry-run", action="store_true", help="Show counts without writing")
    sp.add_argument("--delete-source", action="store_true", help="Wipe source data after copy (destructive)")
    sp.add_argument("-y", "--yes", action="store_true", help="Skip confirmation for --delete-source")
    sp.set_defaults(func=cmd_merge)

    sp = sub.add_parser(
        "delete",
        help="Permanently delete memory data (sqlite + chroma) for a scope",
    )
    sp.add_argument("--scope", required=True, choices=["project", "global", "both"])
    sp.add_argument("-y", "--yes", action="store_true", help="Skip the interactive double-confirmation")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser("web", help="Launch a local Web UI to browse memory")
    sp.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    sp.add_argument("--port", type=int, default=9527, help="Bind port (default 9527; use 0 for a random free port)")
    sp.add_argument("--no-open", action="store_true", help="Do not auto-open a browser tab")
    sp.set_defaults(func=cmd_web)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
