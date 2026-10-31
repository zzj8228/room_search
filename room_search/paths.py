"""All writable state belongs to this project, never the replay app."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def runtime_dir():
    return Path(os.environ.get("PKU_CLASSROOM_DATA_DIR", ROOT / "data")).expanduser().resolve()
