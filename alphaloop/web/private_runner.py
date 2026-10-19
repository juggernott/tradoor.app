"""Customer-hosted, offline backtest entry point. No cloud client or telemetry.

Run in the supplied restricted container. Native invocation is trusted local
execution and does not create an OS sandbox. Inputs and outputs stay local.
"""
import argparse
import json
import os
from pathlib import Path

from alphaloop.web.engine import load_engine
from alphaloop.web.research import Config, csv_frame
from alphaloop.web.store import dump, new_id


def run(csv_path, config_path, output_path, *, factory, source_root):
    csv_path, config_path, output_path = map(Path, (csv_path, config_path, output_path))
    if csv_path.stat().st_size > 5_000_000 or config_path.stat().st_size > 16000:
        raise ValueError("Runner input exceeds size limit")
    csv = csv_path.read_text(encoding="utf-8")
    csv_frame(csv)
    config = Config.model_validate_json(config_path.read_text(encoding="utf-8")).model_dump()
    os.environ["TRADOOR_ENGINE_FACTORY"] = factory
    os.environ["TRADOOR_ALPHACORE_ROOT"] = str(Path(source_root).resolve(strict=True))
    engine = load_engine()
    identifier = new_id()
    result = engine.backtest(csv, config, identifier, "Customer-local input")
    if result.get("id") != identifier or result.get("status") != "completed" or result.get("engine") != engine.name:
        raise ValueError("Private runner result identity mismatch")
    # Entire artifact is private. Do not auto-upload even these selected fields:
    # results themselves can disclose alpha. No code, signals or positions copied.
    fields = {"id", "name", "status", "equity", "curve", "metrics"}
    report = {key: value for key, value in result.items() if key in fields}
    report["privacy"] = "customer-local; no automatic upload"
    encoded = dump(report)
    if len(encoded.encode()) > 2_000_000:
        raise ValueError("Runner report exceeds size limit")
    # Exclusive creation prevents overwriting an existing private file.
    with output_path.open("x", encoding="utf-8") as output:
        output.write(encoded)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("csv", "config", "output", "factory", "source-root"):
        parser.add_argument("--" + option, required=True)
    args = parser.parse_args()
    try:
        run(args.csv, args.config, args.output, factory=args.factory, source_root=args.source_root)
    except Exception:
        # Do not print private adapter tracebacks or input paths into host logs.
        parser.exit(1, "Private research failed; inspect inputs locally. No report uploaded.\n")


if __name__ == "__main__":
    main()
