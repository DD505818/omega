import pandas as pd

from app.trading.engine import FableEngine, RiskEngine, Signal, SignalAction


def bars(closes, volumes=None):
    volumes = volumes or [100.0] * len(closes)
    return pd.DataFrame(
        {
            "open": closes,
            "high": [x + 1 for x in closes],
            "low": [x - 1 for x in closes],
            "close": closes,
            "volume": volumes,
        }
    )


def test_spy_extreme_downside_emits_long():
    engine = FableEngine()
    frame = bars([100.0] * 20 + [90.0])
    signal = engine.evaluate("SPY", frame)
    assert signal.action == SignalAction.LONG


def test_btc_breakout_requires_volume_confirmation():
    engine = FableEngine()
    closes = [100.0] * 20 + [110.0]
    volume = [100.0] * 20 + [120.0]
    signal = engine.evaluate("BTC/USD", bars(closes, volume))
    assert signal.action == SignalAction.NONE


def test_drawdown_circuit_breaker_blocks_new_risk():
    risk = RiskEngine(equity=94_000, peak_equity=100_000, max_drawdown_pct=5)
    signal = Signal("SPY", SignalAction.LONG, "test", 100.0, 2.0, 2.0, "test")
    decision = risk.size(signal)
    assert decision.allowed is False
    assert "drawdown" in decision.reason
