"""Read-only, operator-provisioned historical data grants. No strategy access."""
import hashlib
import json
import os
from pathlib import Path

from alphaloop.web.research import csv_frame


class HistoricalCatalog:
    def __init__(self, workspace):
        self.workspace = workspace or "development-owner"
        configured = os.environ.get("TRADOOR_DATA_CATALOG", "state/data-catalog.json")
        if configured and not Path(configured).is_file():
            configured = ""
        self.path = Path(configured).resolve() if configured else None

    def entries(self):
        if not self.path:
            return []
        entries = json.loads(self.path.read_text(encoding="utf-8"))["datasets"]
        return [entry for entry in entries if self.workspace in entry.get("workspaces", [])
                and entry.get("customer_use_approved") is True and entry.get("rights_reference")]

    def list(self):
        keys = {"id", "label", "description", "kind", "attribution"}
        return [{k: v for k, v in entry.items() if k in keys} for entry in self.entries()]

    def read(self, identifier):
        matches = [entry for entry in self.entries() if entry["id"] == identifier]
        if len(matches) != 1:
            raise KeyError(identifier)
        entry = matches[0]
        root = self.path.parent.resolve()
        source = (root / entry["file"]).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("Catalog file must stay inside its configured root")
        if source.stat().st_size > 5_000_000:
            raise ValueError("Historical panel exceeds 5 MB")
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("Historical data checksum differs from the approved catalog")
        csv = content.decode("utf-8")
        if entry["kind"] != "daily-prices":
            raise ValueError("This version supports daily price panels; feature panels require the feature research adapter")
        csv_frame(csv)
        return {"csv": csv, "source": entry["label"], "catalog_id": entry["id"],
                "sha256": entry["sha256"], "attribution": entry.get("attribution", "")}
