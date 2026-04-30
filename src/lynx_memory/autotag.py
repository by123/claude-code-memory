"""Rule-based automatic tag suggestion for persisted turns."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

_USER_ROLE_PATTERNS = [
    re.compile(r"(?:我是|我是一名|我是一位|我作为|作为)([^，。,；;\n]{1,24})"),
    re.compile(
        r"(?:i am|i'm|my role is)\s+(?:(?:a|an|the)\s+)?([a-zA-Z][a-zA-Z /_-]{1,24}?)"
        r"(?=\s+(?:working on|who|and|at)\b|[,.;\n]|$)",
        re.IGNORECASE,
    ),
]

_USER_PREFERENCE_PATTERNS = [
    re.compile(r"(?:我喜欢|我偏好|我习惯|我通常会)([^，。,；;\n]{1,28})"),
    re.compile(r"(?:我不喜欢|我讨厌|我避免)([^，。,；;\n]{1,28})"),
    re.compile(
        r"(?:i prefer|i like|i usually|i tend to)\s+([a-zA-Z][^,.;\n]{1,32})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:i don't like|i avoid|i hate)\s+([a-zA-Z][^,.;\n]{1,32})",
        re.IGNORECASE,
    ),
]

_PATH_RE = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|json|toml|ya?ml|md)"
)

_STACK_KEYWORDS = {
    "python": "stack:python",
    "fastapi": "stack:fastapi",
    "react": "stack:react",
    "typescript": "stack:typescript",
    "sqlite": "stack:sqlite",
    "chroma": "stack:chroma",
}

_GENERIC_PARTS = {
    "src",
    "lib",
    "app",
    "apps",
    "packages",
    "components",
    "hooks",
    "assets",
    "web",
    "tests",
}

_GENERIC_STEMS = {"index", "main", "app", "__init__"}


def _clean_value(value: str) -> str:
    value = " ".join(value.strip().strip("`'\"").split())
    return value.rstrip("，。,；;:：")


def _append(
    out: Dict[str, Dict[str, object]],
    *,
    name: str,
    kind: str,
    confidence: float,
) -> None:
    clean = _clean_value(name)
    if not clean:
        return
    prev = out.get(clean)
    if prev is None or float(prev["confidence"]) < confidence:
        out[clean] = {"name": clean, "kind": kind, "confidence": confidence}


def _extract_user_role(user_msg: str, out: Dict[str, Dict[str, object]]) -> None:
    for pattern in _USER_ROLE_PATTERNS:
        for match in pattern.finditer(user_msg):
            role = _clean_value(match.group(1))
            if len(role) < 2:
                continue
            _append(out, name=f"role:{role}", kind="user.role", confidence=0.96)


def _extract_user_preferences(user_msg: str, out: Dict[str, Dict[str, object]]) -> None:
    for pattern in _USER_PREFERENCE_PATTERNS:
        for match in pattern.finditer(user_msg):
            pref = _clean_value(match.group(1))
            if len(pref) < 2:
                continue
            _append(out, name=f"preference:{pref}", kind="user.preference", confidence=0.9)


def _extract_project_tags(text: str, cwd: Optional[str], out: Dict[str, Dict[str, object]]) -> None:
    if cwd:
        repo = Path(cwd).name.strip()
        if repo:
            _append(out, name=f"repo:{repo.lower()}", kind="project.repo", confidence=0.99)
    lower = text.lower()
    for keyword, tag in _STACK_KEYWORDS.items():
        if keyword in lower:
            _append(out, name=tag, kind="project.stack", confidence=0.82)


def _module_name_from_path(path_text: str) -> Optional[str]:
    parts = [p for p in path_text.split("/") if p and p not in (".", "..")]
    if len(parts) < 2:
        return None
    stem = Path(parts[-1]).stem.lower()
    if stem not in _GENERIC_STEMS:
        return stem
    meaningful = [p.lower() for p in parts[:-1] if p.lower() not in _GENERIC_PARTS]
    if meaningful:
        return meaningful[-1]
    return None


def _extract_module_tags(text: str, out: Dict[str, Dict[str, object]]) -> None:
    for raw_path in _PATH_RE.findall(text):
        module = _module_name_from_path(raw_path)
        if not module:
            continue
        _append(out, name=f"module:{module}", kind="module.feature", confidence=0.78)


def suggest_tags(user_msg: str, assistant_msg: str, cwd: Optional[str] = None) -> List[Dict[str, object]]:
    """Return structured tags inferred from one user/assistant turn."""
    text = f"{user_msg}\n{assistant_msg}"
    out: Dict[str, Dict[str, object]] = {}
    _extract_user_role(user_msg, out)
    _extract_user_preferences(user_msg, out)
    _extract_project_tags(text, cwd, out)
    _extract_module_tags(text, out)
    return sorted(out.values(), key=lambda item: (str(item["kind"]), str(item["name"])))
