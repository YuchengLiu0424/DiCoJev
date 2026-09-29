"""Optional FastAPI surface for the stable v5 decision endpoint."""

from __future__ import annotations

from typing import Any

from ..schemas import DecisionRequest, DecisionResponse


def create_app(runtime: Any):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as error:  # pragma: no cover - depends on optional install
        raise RuntimeError('install dicojev with the "api" extra') from error

    app = FastAPI(title="DiCoJev", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "milestone": "v5"}

    @app.post("/v1/decide", response_model=DecisionResponse)
    async def decide(request: DecisionRequest) -> DecisionResponse:
        try:
            return await runtime.decide(request)
        except Exception as error:
            raise HTTPException(status_code=503, detail=type(error).__name__) from error

    return app
