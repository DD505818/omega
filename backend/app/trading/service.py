from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from .alpaca_adapter import AlpacaGateway
from .config import TradingSettings
from .engine import FableEngine, RiskEngine, SignalAction, correlated_entry_count


class FableTradingService:
    CORRELATED = {"SPY", "QQQ", "BTC/USD"}

    def __init__(self, settings: TradingSettings | None = None) -> None:
        self.settings = settings or TradingSettings()
        self.engine = FableEngine()

    @staticmethod
    def _latest_timestamp(frame: pd.DataFrame) -> datetime:
        if frame.empty or "timestamp" not in frame.columns:
            raise ValueError("market data frame has no timestamps")
        ts = pd.Timestamp(frame["timestamp"].iloc[-1])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.to_pydatetime().astimezone(timezone.utc)

    def _validate_freshness(
        self,
        frames: dict[str, pd.DataFrame],
        *,
        stock_market_open: bool,
    ) -> None:
        now = datetime.now(timezone.utc)
        for symbol, frame in frames.items():
            age = now - self._latest_timestamp(frame)

            if symbol == "BTC/USD":
                max_age = timedelta(hours=2)
            elif stock_market_open and symbol in {"SPY", "QQQ"}:
                max_age = timedelta(minutes=45)
            elif stock_market_open:
                max_age = timedelta(hours=6)
            else:
                # Allows normal weekend/holiday closures without masking stale
                # intraday data while the equities market is actually open.
                max_age = timedelta(days=4)

            if age < timedelta(0):
                raise ValueError(f"{symbol} market data timestamp is in the future")
            if age > max_age:
                raise ValueError(
                    f"{symbol} market data is stale: age={age}, max_age={max_age}"
                )

    def snapshot(self) -> dict:
        gateway = AlpacaGateway(self.settings)
        frames = gateway.fetch_fable_universe()
        market_open = gateway.market_is_open()
        self._validate_freshness(frames, stock_market_open=market_open)
        signals = self.engine.evaluate_many(frames)

        risk = RiskEngine(
            equity=self.settings.account_equity,
            peak_equity=self.settings.peak_equity,
            max_drawdown_pct=self.settings.max_drawdown_pct,
            risk_per_trade_pct=self.settings.risk_per_trade_pct,
            max_gross_exposure_pct=self.settings.max_gross_exposure_pct,
            stop_atr_multiplier=self.settings.stop_atr_multiplier,
        )

        active_corr = correlated_entry_count(signals, self.CORRELATED)
        decisions = []
        for signal in signals:
            if (
                signal.symbol in self.CORRELATED
                and signal.action in {SignalAction.LONG, SignalAction.SHORT}
                and active_corr > 2
            ):
                decisions.append(
                    {
                        **signal.to_dict(),
                        "allowed": False,
                        "quantity": 0.0,
                        "risk_reason": "correlation cap: >2 simultaneous correlated entries",
                    }
                )
                continue

            d = risk.size(signal, fractional=True)
            decisions.append(
                {
                    **signal.to_dict(),
                    "allowed": d.allowed,
                    "quantity": d.quantity,
                    "stop_distance": d.stop_distance,
                    "risk_reason": d.reason,
                }
            )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "paper_mode": self.settings.paper_mode,
            "execute_orders": self.settings.execute_orders,
            "stock_market_open": market_open,
            "drawdown_pct": risk.drawdown_pct,
            "signals": decisions,
        }

    def run_once(self) -> dict:
        snapshot = self.snapshot()
        if not self.settings.execute_orders:
            snapshot["execution"] = "DRY_RUN"
            return snapshot

        # Deliberately refuse unattended multi-order execution in v1.
        # The snapshot is deterministic and can be reviewed/approved by a
        # higher-level Ω∆V execution policy before calling AlpacaGateway.
        snapshot["execution"] = "APPROVAL_REQUIRED"
        return snapshot
