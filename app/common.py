import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
RUNNER_TEMPLATE_DIR = Path(os.environ.get("RUNNER_TEMPLATE_DIR", "/opt/runner"))
RUNNER_DIR = DATA_DIR / "runner"
CONFIG_PATH = DATA_DIR / "config.json"
STATUS_PATH = DATA_DIR / "status.json"
LOG_DIR = DATA_DIR / "logs"
RUNNER_LOG_PATH = LOG_DIR / "runner.log"
APP_LOG_PATH = LOG_DIR / "app.log"


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)
