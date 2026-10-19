"""Operator-selected private workspace configuration, never request-controlled."""
import json
import os
from pathlib import Path
import re


def configure_workspace(filename):
    path = Path(filename).resolve(strict=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {"id", "database", "engine_factory", "source_root", "token_env", "host"}
    allowed = required | {"data_catalog"}
    if set(config) - allowed or not required <= set(config):
        raise ValueError("Workspace configuration has missing or unknown fields")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", config["id"]):
        raise ValueError("Invalid workspace identity")
    token = os.environ.get(config["token_env"], "")
    if len(token) < 32:
        raise ValueError("Workspace owner token is missing or too short")
    def relative(value):
        result = Path(value)
        return str((result if result.is_absolute() else path.parent / result).resolve())
    # Each manifest is used in its own API and worker processes. Explicit values
    # replace inherited private source settings instead of falling back to v12.
    os.environ.update(TRADOOR_WORKSPACE_ID=config["id"],
        TRADOOR_DB=relative(config["database"]),
        TRADOOR_ENGINE_FACTORY=config["engine_factory"],
        TRADOOR_ALPHACORE_ROOT=relative(config["source_root"]),
        TRADOOR_ADMIN_TOKEN=token, TRADOOR_HOST=config["host"],
        TRADOOR_DATA_CATALOG=relative(config["data_catalog"]) if config.get("data_catalog") else "")
    return os.environ["TRADOOR_DB"]
