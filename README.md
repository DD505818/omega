# Ω∆V — FINAL ELITE EDITION v8.2

Autonomous Trading Intelligence · Precision-Engineered · Production-Hardened

## Status

This repository is a self-hosted **paper-first autonomous trading command center** scaffold for Ω∆V v8.2. It includes deployable Docker infrastructure, a FastAPI backend, a Next.js Aurora Glass terminal shell, AEGIS-style risk endpoints, SQRA/Dominance/AFM service stubs, and production safety boundaries.

> Live trading is blocked by default. Backtest/Monte Carlo claims are treated as research hypotheses until independently reproduced under controlled validation.

## Quick Start

```bash
cp .env.example .env
chmod +x master-deploy.sh
./master-deploy.sh
```

Dashboard: `http://localhost:3000`  
API Health: `http://localhost:8000/api/health`

## Architecture

```text
Market Data → GPU Feature Engine → CRRP → SQRA → Agent Swarm → Dominance Protocol → AEGIS → VULTURE → Truth-Core
```

## Safety Defaults

- `PAPER_MODE=true`
- `LIVE_TRADING_ENABLED=false`
- Secret placeholders rejected during deploy
- Kill switch endpoint present
- Risk limits enforced server-side
- Aggressive profile ships as paper-validation config only

## Repo Structure

```text
backend/       FastAPI API, routers, services, SQRA/Dominance/AFM
frontend/      Next.js 15 terminal UI shell
nginx/         reverse proxy
scripts/       validation helpers
docs/          final spec and aggressive profile notes
.github/       CI workflow
```

## Aggressive Paper Profile

Use only for paper/shadow validation:

```bash
cp .env.aggressive-paper.example .env
./master-deploy.sh
```

See `docs/AGGRESSIVE_ZERO_RUIN_PROFILE.md` for constraints and acceptance gates.
