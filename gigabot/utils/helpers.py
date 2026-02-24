"""Utility functions for GigaBot."""

from pathlib import Path
from datetime import datetime


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_path() -> Path:
    return ensure_dir(Path.home() / ".gigabot")


def get_workspace_path(workspace: str | None = None) -> Path:
    if workspace:
        path = Path(workspace).expanduser()
    else:
        path = Path.home() / ".gigabot" / "workspace"
    return ensure_dir(path)


def timestamp() -> str:
    return datetime.now().isoformat()


def truncate_string(s: str, max_len: int = 100, suffix: str = "...") -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - len(suffix)] + suffix


def safe_filename(name: str) -> str:
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, "_")
    return name.strip()


def parse_session_key(key: str) -> tuple[str, str]:
    parts = key.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid session key: {key}")
    return parts[0], parts[1]
