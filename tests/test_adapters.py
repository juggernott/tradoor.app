import pytest

from alphaloop.adapters.base import AdapterConfigError
from alphaloop.adapters.ccxt_data import _freq_to_ms
from alphaloop.adapters.cryptoquant import CryptoQuantAdapter
from alphaloop.adapters.elfa import ElfaAdapter
from alphaloop.adapters.nansen import NansenAdapter


@pytest.mark.parametrize("adapter_cls", [ElfaAdapter, NansenAdapter, CryptoQuantAdapter])
def test_skeleton_adapters_require_api_key(adapter_cls, monkeypatch):
    for var in (
        "ALPHALOOP_ELFA_API_KEY",
        "ALPHALOOP_NANSEN_API_KEY",
        "ALPHALOOP_CRYPTOQUANT_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(AdapterConfigError):
        adapter_cls()


@pytest.mark.parametrize("adapter_cls", [ElfaAdapter, NansenAdapter, CryptoQuantAdapter])
def test_skeleton_adapters_fetch_raises_not_implemented(adapter_cls):
    adapter = adapter_cls(api_key="fake-key-for-test")
    with pytest.raises(NotImplementedError, match="TODO"):
        adapter.fetch(["price"], ["BTC/USDT"], "2024-01-01", "2024-01-02", "1h")


def test_skeleton_adapters_declare_protocol_attrs():
    adapter = ElfaAdapter(api_key="fake")
    assert adapter.name == "elfa"
    assert isinstance(adapter.provides, set)
    assert isinstance(adapter.point_in_time, bool)


def test_freq_to_ms():
    assert _freq_to_ms("1h") == 3_600_000
    assert _freq_to_ms("15m") == 15 * 60_000
    assert _freq_to_ms("1d") == 86_400_000


def test_freq_to_ms_rejects_unknown_unit():
    with pytest.raises(ValueError):
        _freq_to_ms("1x")
