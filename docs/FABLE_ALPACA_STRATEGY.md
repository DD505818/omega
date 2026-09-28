# Fable / Alpaca Strategy Module

This module implements the strategy family discussed in the Ray Fu Claude/Fable trading-bot guide as a **paper-first Ω∆V component**.

## Strategy map

| Symbol | Timeframe | Rule |
|---|---|---|
| SPY | 15m | 20-bar z-score mean reversion at ±1.5σ |
| QQQ | 15m | 20-bar z-score mean reversion at ±1.8σ |
| BTC/USD | 1h | prior-20-bar breakout + >=1.5x volume |
| GLD | 4h | 50/200 EMA crossover |
| USO | 4h | 50/200 EMA crossover |

BTC downside breakouts are modeled as **EXIT**, not short entries, because spot crypto shortability must not be assumed.

## Safety controls

- Paper mode is the default.
- Live mode requires both `LIVE_TRADING_ENABLED=true` and `OMEGA_ACK_LIVE_TRADING=I_UNDERSTAND`.
- Order submission is independently blocked unless `EXECUTE_ORDERS=true`.
- New risk is rejected when the portfolio drawdown circuit breaker is reached.
- ATR-based sizing caps risk per trade.
- Gross notional exposure is capped.
- SPY / QQQ / BTC simultaneous-entry correlation is capped.
- The first version returns an approval-required execution plan rather than firing a basket of unattended orders.

## Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
uvicorn app.main:app --reload
```

Then inspect:

```text
GET  /api/strategies/fable/snapshot
POST /api/strategies/fable/run-once
```

Use paper credentials in `.env`. Keep `EXECUTE_ORDERS=false` until the strategy has passed replay/backtest, paper execution, slippage, restart-recovery, and kill-switch tests.
