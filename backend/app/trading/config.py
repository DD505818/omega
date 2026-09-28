from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    paper_mode: bool = Field(default=True, alias="PAPER_MODE")
    live_trading_enabled: bool = Field(default=False, alias="LIVE_TRADING_ENABLED")
    live_ack: str = Field(default="", alias="OMEGA_ACK_LIVE_TRADING")
    execute_orders: bool = Field(default=False, alias="EXECUTE_ORDERS")

    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")

    account_equity: float = Field(default=100_000.0, alias="FABLE_ACCOUNT_EQUITY")
    peak_equity: float = Field(default=100_000.0, alias="FABLE_PEAK_EQUITY")
    max_drawdown_pct: float = Field(default=5.0, alias="FABLE_MAX_DRAWDOWN_PCT")
    risk_per_trade_pct: float = Field(default=0.5, alias="FABLE_RISK_PER_TRADE_PCT")
    max_gross_exposure_pct: float = Field(default=100.0, alias="FABLE_MAX_GROSS_EXPOSURE_PCT")
    stop_atr_multiplier: float = Field(default=2.0, alias="FABLE_STOP_ATR_MULTIPLIER")

    @model_validator(mode="after")
    def enforce_live_interlock(self) -> "TradingSettings":
        if not self.paper_mode:
            if not self.live_trading_enabled:
                raise ValueError("PAPER_MODE=false requires LIVE_TRADING_ENABLED=true")
            if self.live_ack != "I_UNDERSTAND":
                raise ValueError(
                    "Live mode requires OMEGA_ACK_LIVE_TRADING=I_UNDERSTAND"
                )
        return self
