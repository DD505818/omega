from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from .config import TradingSettings
from .engine import Signal, SignalAction


def _bars_to_frame(bars) -> pd.DataFrame:
    rows = []
    for bar in bars:
        rows.append(
            {
                "timestamp": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


class AlpacaGateway:
    def __init__(self, settings: TradingSettings) -> None:
        self.settings = settings
        if not settings.alpaca_api_key or not settings.alpaca_secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")

        self.stock_data = StockHistoricalDataClient(
            settings.alpaca_api_key, settings.alpaca_secret_key
        )
        self.crypto_data = CryptoHistoricalDataClient(
            settings.alpaca_api_key, settings.alpaca_secret_key
        )
        self.trading = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            paper=settings.paper_mode,
        )

    def stock_frame(
        self,
        symbol: str,
        *,
        timeframe: TimeFrame,
        lookback_days: int,
    ) -> pd.DataFrame:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=datetime.now(timezone.utc) - timedelta(days=lookback_days),
        )
        result = self.stock_data.get_stock_bars(request)
        return _bars_to_frame(result[symbol])

    def crypto_frame(
        self,
        symbol: str = "BTC/USD",
        *,
        lookback_days: int = 7,
    ) -> pd.DataFrame:
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Hour,
            start=datetime.now(timezone.utc) - timedelta(days=lookback_days),
        )
        result = self.crypto_data.get_crypto_bars(request)
        return _bars_to_frame(result[symbol])

    def fetch_fable_universe(self) -> dict[str, pd.DataFrame]:
        return {
            "SPY": self.stock_frame("SPY", timeframe=TimeFrame(15, TimeFrameUnit.Minute), lookback_days=7),
            "QQQ": self.stock_frame("QQQ", timeframe=TimeFrame(15, TimeFrameUnit.Minute), lookback_days=7),
            "BTC/USD": self.crypto_frame("BTC/USD", lookback_days=7),
            "GLD": self.stock_frame("GLD", timeframe=TimeFrame(4, TimeFrameUnit.Hour), lookback_days=365),
            "USO": self.stock_frame("USO", timeframe=TimeFrame(4, TimeFrameUnit.Hour), lookback_days=365),
        }

    def submit_entry(self, signal: Signal, quantity: float):
        if not self.settings.execute_orders:
            raise RuntimeError("EXECUTE_ORDERS=false; order submission blocked")
        if signal.action not in {SignalAction.LONG, SignalAction.SHORT}:
            raise ValueError("Only entry signals can be submitted")

        side = OrderSide.BUY if signal.action == SignalAction.LONG else OrderSide.SELL
        tif = TimeInForce.GTC if signal.symbol == "BTC/USD" else TimeInForce.DAY
        order = MarketOrderRequest(
            symbol=signal.symbol.replace("/", ""),
            qty=quantity,
            side=side,
            time_in_force=tif,
        )
        return self.trading.submit_order(order_data=order)

    def close_symbol(self, symbol: str):
        if not self.settings.execute_orders:
            raise RuntimeError("EXECUTE_ORDERS=false; order submission blocked")
        return self.trading.close_position(symbol.replace("/", ""))
