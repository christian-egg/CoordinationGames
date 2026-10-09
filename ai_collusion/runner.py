"""Load API keys and model configurations for coordination-game runs."""
from __future__ import annotations

from pathlib import Path

import yaml

from .client import ModelConfig

REPO_ENV = Path(__file__).resolve().parents[1] / ".env"


def load_repo_env(path: Path = REPO_ENV) -> bool:
    """Load API keys from the repo's .env into os.environ (existing variables win).

    Returns True if the file was found and read. Missing file or missing python-dotenv is not an error:
    keys can still come from the shell environment.
    """
    if not path.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    load_dotenv(dotenv_path=path, override=False)
    return True


def load_models(path: str | Path, only: list[str] | None = None) -> list[ModelConfig]:
    load_repo_env()
    data = yaml.safe_load(Path(path).read_text())
    defaults = data.get("defaults", {}) or {}
    models = [ModelConfig.from_dict(m, defaults) for m in data["models"]]
    if only:
        wanted = set(only)
        models = [m for m in models if m.name in wanted]
        missing = wanted - {m.name for m in models}
        if missing:
            raise SystemExit(f"models not found in {path}: {sorted(missing)}")
    return models
