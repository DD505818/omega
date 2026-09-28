from __future__ import annotations

from datetime import datetime, timezone

from .alpaca_adapter import AlpacaGateway
from .config import TradingSettings
from .engine import FableEngine, RiskEngine, SignalAction, correlated_entry_count


class FableTradingService:
    CORRELATED = {"SPY", "QQQ", "BTC/USD"}

    def __init__(self, settings: TradingSettings | None = None) -> None:
        self.settings = settings or TradingSettings()
        self.engine = FableEngine()

    def snapshot(self) -> dict:
        gateway = AlpacaGateway(self.settings)
        frames = gateway.fetch_fable_universe()
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
