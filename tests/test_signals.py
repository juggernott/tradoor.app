import pandas as pd
import pytest

from alphaloop.backtest.signals import SignalExpressionError, evaluate_signal


@pytest.fixture
def frame():
    return pd.DataFrame(
        {"price.ohlcv.close": [1, 2, 3, 4, 5, 4, 3, 2, 1, 0.5], "price.ohlcv.volume": [10] * 10}
    )


def test_short_name_access(frame):
    result = evaluate_signal("close > 3", frame)
    assert list(result) == [False, False, False, True, True, True, False, False, False, False]


def test_rolling_method(frame):
    result = evaluate_signal("close > close.rolling(3).mean()", frame)
    assert isinstance(result, pd.Series)
    assert len(result) == len(frame)


def test_boolean_and(frame):
    result = evaluate_signal("close > 2 and volume > 5", frame)
    assert result.iloc[3]  # close=4, volume=10


def test_arithmetic(frame):
    result = evaluate_signal("close * 2", frame)
    assert result.iloc[0] == 2


def test_unknown_identifier_rejected(frame):
    with pytest.raises(SignalExpressionError, match="unknown identifier"):
        evaluate_signal("nonexistent_column > 1", frame)


def test_disallowed_call_rejected(frame):
    with pytest.raises(SignalExpressionError, match="not whitelisted"):
        evaluate_signal("close.to_csv('/tmp/x')", frame)


def test_arbitrary_code_execution_rejected(frame):
    with pytest.raises(SignalExpressionError):
        evaluate_signal("__import__('os').system('echo hi')", frame)


def test_syntax_error_rejected(frame):
    with pytest.raises(SignalExpressionError, match="invalid signal expression"):
        evaluate_signal("close >", frame)


def test_full_dotted_name_fallback():
    frame = pd.DataFrame({"onchain.mvrv": [1, 2, 3]})
    result = evaluate_signal("onchain_mvrv > 1", frame)
    assert list(result) == [False, True, True]
