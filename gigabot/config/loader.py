"""Configuration loading utilities."""

import json
from pathlib import Path

from gigabot.config.schema import Config


def get_config_path() -> Path:
    return Path.home() / ".gigabot" / "config.json"


def get_data_dir() -> Path:
    path = Path.home() / ".gigabot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(config_path: Path | None = None) -> Config:
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
