from alphaloop.compile.dedup import find_similar
from alphaloop.journal.store import JournalEntry


def test_exact_duplicate_detected(timeseries_spec):
    entry = JournalEntry(run_dir=None, spec=timeseries_spec, verdict="KILL", grade="F")
    matches = find_similar(timeseries_spec, [entry])
    assert len(matches) == 1
    assert matches[0].exact
    assert matches[0].similarity == 1.0


def test_unrelated_spec_not_flagged(timeseries_spec, crosssectional_spec):
    entry = JournalEntry(run_dir=None, spec=crosssectional_spec, verdict="KILL", grade="F")
    matches = find_similar(timeseries_spec, [entry], threshold=0.75)
    assert matches == []


def test_similar_spec_flagged_but_not_exact(timeseries_spec):
    tweaked = timeseries_spec.model_copy(update={"name": "tweaked"})
    entry = JournalEntry(run_dir=None, spec=timeseries_spec, verdict="ITERATE", grade="D")
    matches = find_similar(tweaked, [entry], threshold=0.5)
    assert len(matches) == 1
    assert matches[0].exact  # same content_hash since only `name` changed
