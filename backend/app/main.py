from fastapi import FastAPI, HTTPException

from app.trading.service import FableTradingService

app = FastAPI(title="Ω∆V Fable Strategy API", version="1.0.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "omega-fable"}


@app.get("/api/strategies/fable/snapshot")
def fable_snapshot() -> dict:
    try:
        return FableTradingService().snapshot()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/strategies/fable/run-once")
def fable_run_once() -> dict:
    try:
        return FableTradingService().run_once()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
