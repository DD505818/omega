from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import floor
from typing import Iterable

import numpy as np
import pandas as pd


class SignalAction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"
    NONE = "NONE"


@dataclass(frozen=True)
class Signal:
    symbol: str
    action: SignalAction
    strategy: str
    price: float
    atr: float | None
    strength: float
    reason: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["action"] = self.action.value
        return payload


def _require_ohlcv(frame: pd.DataFrame, minimum: int) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    if len(frame) < minimum:
        raise ValueError(f"Need at least {minimum} bars, got {len(frame)}")
    clean = frame.copy()
    for col in required:
        clean[col] = pd.to_numeric(clean[col], errors="coerce")
    clean = clean.dropna(subset=list(required))
    if len(clean) < minimum:
        raise ValueError("Not enough valid OHLCV rows after cleaning")
    return clean


def atr(frame: pd.DataFrame, period: int = 14) -> float:
    df = _require_ohlcv(frame, period + 1)
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.tail(period).mean())


class FableEngine:
    """Ray Fu / Fable-inspired multi-regime signal engine.

    Pure signal logic only. Brokerage execution and portfolio risk controls live
    outside this class so signals are deterministic and straightforward to test.
    """

    MEAN_REVERSION = {"SPY": 1.5, "QQQ": 1.8}

    def evaluate(self, symbol: str, frame: pd.DataFrame) -> Signal:
        normalized = symbol.upper().replace("-", "/")
        if normalized in self.MEAN_REVERSION:
            return self._mean_reversion(normalized, frame)
        if normalized in {"BTC/USD", "BTCUSD"}:
            return self._btc_breakout("BTC/USD", frame)
        if normalized in {"GLD", "USO"}:
            return self._ema_cross(normalized, frame)
        raise ValueError(f"Unsupported Fable symbol: {symbol}")

    def evaluate_many(self, frames: dict[str, pd.DataFrame]) -> list[Signal]:
        return [self.evaluate(symbol, frame) for symbol, frame in frames.items()]

    def _mean_reversion(self, symbol: str, frame: pd.DataFrame) -> Signal:
        df = _require_ohlcv(frame, 21)
        close = df["close"]
        mean = float(close.tail(20).mean())
        std = float(close.tail(20).std(ddof=0))
        price = float(close.iloc[-1])
        threshold = self.MEAN_REVERSION[symbol]
        current_atr = atr(df)

        if std <= 0 or not np.isfinite(std):
            return Signal(symbol, SignalAction.NONE, "mean_reversion_15m", price, current_atr, 0.0, "zero volatility")

        z = (price - mean) / std
        if z <= -threshold:
            action = SignalAction.LONG
        elif z >= threshold:
            action = SignalAction.SHORT
        else:
            action = SignalAction.NONE

        return Signal(
            symbol=symbol,
            action=action,
            strategy="mean_reversion_15m",
            price=price,
            atr=current_atr,
            strength=abs(float(z)) / threshold,
            reason=f"z={z:.3f}; threshold=±{threshold:.1f}; sma20={mean:.4f}",
        )

    def _btc_breakout(self, symbol: str, frame: pd.DataFrame) -> Signal:
        df = _require_ohlcv(frame, 21)
        current = df.iloc[-1]
        prior = df.iloc[-21:-1]
        high20 = float(prior["high"].max())
        low20 = float(prior["low"].min())
        avg_vol = float(prior["volume"].mean())
        volume_ratio = float(current["volume"] / avg_vol) if avg_vol > 0 else 0.0
        price = float(current["close"])
        current_atr = atr(df)

        if price > high20 and volume_ratio >= 1.5:
            action = SignalAction.LONG
            reason = f"breakout>{high20:.2f}; volume={volume_ratio:.2f}x"
        elif price < low20 and volume_ratio >= 1.5:
            # Alpaca spot crypto cannot be assumed shortable. Treat downside as
            # a risk-management exit, not a synthetic short.
            action = SignalAction.EXIT
            reason = f"breakdown<{low20:.2f}; volume={volume_ratio:.2f}x"
        else:
            action = SignalAction.NONE
            reason = f"range={low20:.2f}-{high20:.2f}; volume={volume_ratio:.2f}x"

        return Signal(symbol, action, "btc_breakout_1h", price, current_atr, volume_ratio / 1.5, reason)

    def _ema_cross(self, symbol: str, frame: pd.DataFrame) -> Signal:
        df = _require_ohlcv(frame, 201)
        close = df["close"]
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        prev_fast, fast = float(ema50.iloc[-2]), float(ema50.iloc[-1])
        prev_slow, slow = float(ema200.iloc[-2]), float(ema200.iloc[-1])
        price = float(close.iloc[-1])
        current_atr = atr(df)

        crossed_up = prev_fast <= prev_slow and fast > slow
        crossed_down = prev_fast >= prev_slow and fast < slow

        if crossed_up:
            action = SignalAction.LONG
        elif crossed_down:
            action = SignalAction.EXIT
        else:
            action = SignalAction.NONE

        gap = abs(fast - slow) / price if price else 0.0
        return Signal(
            symbol,
            action,
            "ema_cross_4h",
            price,
            current_atr,
            gap,
            f"ema50={fast:.4f}; ema200={slow:.4f}; crossover={action.value}",
        )


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    quantity: float
    stop_distance: float
    reason: str


class RiskEngine:
    def __init__(
        self,
        *,
        equity: float,
        peak_equity: float,
        max_drawdown_pct: float = 5.0,
        risk_per_trade_pct: float = 0.5,
        max_gross_exposure_pct: float = 100.0,
        stop_atr_multiplier: float = 2.0,
    ) -> None:
        self.equity = equity
        self.peak_equity = peak_equity
        self.max_drawdown_pct = max_drawdown_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_gross_exposure_pct = max_gross_exposure_pct
        self.stop_atr_multiplier = stop_atr_multiplier

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 100.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)

    def size(
        self,
        signal: Signal,
        *,
        current_gross_notional: float = 0.0,
        fractional: bool = True,
    ) -> RiskDecision:
        if signal.action in {SignalAction.NONE, SignalAction.EXIT}:
            return RiskDecision(False, 0.0, 0.0, "signal does not open risk")
        if self.drawdown_pct >= self.max_drawdown_pct:
            return RiskDecision(False, 0.0, 0.0, "portfolio drawdown circuit breaker")
        if not signal.atr or signal.atr <= 0:
            return RiskDecision(False, 0.0, 0.0, "invalid ATR")

        gross_cap = self.equity * self.max_gross_exposure_pct / 100.0
        remaining_notional = max(0.0, gross_cap - current_gross_notional)
        if remaining_notional <= 0:
            return RiskDecision(False, 0.0, 0.0, "gross exposure cap reached")

        stop_distance = signal.atr * self.stop_atr_multiplier
        risk_budget = self.equity * self.risk_per_trade_pct / 100.0
        by_risk = risk_budget / stop_distance
        by_notional = remaining_notional / signal.price
        qty = min(by_risk, by_notional)
        qty = round(qty, 6) if fractional else float(floor(qty))

        if qty <= 0:
            return RiskDecision(False, 0.0, stop_distance, "position size rounded to zero")
        return RiskDecision(True, qty, stop_distance, "within risk limits")


def correlated_entry_count(signals: Iterable[Signal], symbols: set[str]) -> int:
    return sum(
        1
        for s in signals
        if s.symbol in symbols and s.action in {SignalAction.LONG, SignalAction.SHORT}
    )
