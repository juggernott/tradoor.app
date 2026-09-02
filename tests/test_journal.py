from alphaloop.core.loop import run_backtest
from alphaloop.core.resolver import Resolver
from alphaloop.journal.bundle import export_bundle, verify_bundle
from alphaloop.journal.store import JournalStore
from alphaloop.validate.trials import TrialRegistry


def _run(tmp_path, spec, mock_registry):
    resolver = Resolver(["mock"], cache_dir=tmp_path / "cache", registry=mock_registry)
    trials = TrialRegistry(tmp_path / "trials.json")
    return run_backtest(spec, resolver, trial_registry=trials, registry=mock_registry)


def test_record_creates_run_directory(tmp_path, timeseries_spec, mock_registry):
    outcome = _run(tmp_path, timeseries_spec, mock_registry)
    store = JournalStore(tmp_path / "journal")
    entry = store.record(timeseries_spec, outcome, "2024-06-01")

    assert entry.run_dir.exists()
    assert (entry.run_dir / "spec.yaml").exists()
    assert (entry.run_dir / "scorecard.md").exists()
    assert (entry.run_dir / "equity_curve.png").exists()
    assert (entry.run_dir / "verdict").read_text().strip() == outcome.report.verdict


def test_record_never_collides_on_same_day(tmp_path, timeseries_spec, mock_registry):
    store = JournalStore(tmp_path / "journal")
    outcome1 = _run(tmp_path, timeseries_spec, mock_registry)
    entry1 = store.record(timeseries_spec, outcome1, "2024-06-01")
    outcome2 = _run(tmp_path, timeseries_spec, mock_registry)
    entry2 = store.record(timeseries_spec, outcome2, "2024-06-01")
    assert entry1.run_dir != entry2.run_dir


def test_list_entries_filters_by_verdict(tmp_path, timeseries_spec, mock_registry):
    store = JournalStore(tmp_path / "journal")
    outcome = _run(tmp_path, timeseries_spec, mock_registry)
    store.record(timeseries_spec, outcome, "2024-06-01")

    all_entries = store.list_entries()
    assert len(all_entries) == 1
    matching = store.list_entries(verdict=outcome.report.verdict)
    assert len(matching) == 1
    other = store.list_entries(verdict="__nonexistent__")
    assert len(other) == 0


def test_bundle_export_and_verify(tmp_path, timeseries_spec, mock_registry):
    store = JournalStore(tmp_path / "journal")
    outcome = _run(tmp_path, timeseries_spec, mock_registry)
    entry = store.record(timeseries_spec, outcome, "2024-06-01")

    zip_path = export_bundle(entry.run_dir, tmp_path / "bundle.zip")
    assert zip_path.exists()
    assert verify_bundle(zip_path)


def test_bundle_verify_fails_on_tamper(tmp_path, timeseries_spec, mock_registry):
    import zipfile

    store = JournalStore(tmp_path / "journal")
    outcome = _run(tmp_path, timeseries_spec, mock_registry)
    entry = store.record(timeseries_spec, outcome, "2024-06-01")
    zip_path = export_bundle(entry.run_dir, tmp_path / "bundle.zip")

    # tamper: rewrite the zip with one file's content changed
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.endswith("verdict"):
                data = b"TAMPERED"
            dst.writestr(item, data)

    assert not verify_bundle(tampered)
