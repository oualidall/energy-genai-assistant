"""FastAPI application for the Energy GenAI Assistant.

Phase 0 exposes a minimal, testable surface:

GET  /healthz   liveness / readiness probe
POST /ask       answer a natural-language question (stubbed until Phase 2-3)

The RAG + text-to-SQL agent is wired in later phases; keeping the HTTP contract
stable from the start lets CI and the deployment pipeline be built first.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from src.api.schemas import AskRequest, AskResponse, HealthResponse
from src.config import settings

logging.basicConfig(
    level=settings.log_level,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Energy GenAI Assistant",
    description=(
        "Ask questions in natural language about RTE electricity data. "
        "An agent routes between document retrieval (RAG) and text-to-SQL on BigQuery."
    ),
    version="0.1.0",
)


@app.get("/healthz", response_model=HealthResponse, tags=["ops"])
async def healthz() -> HealthResponse:
    """Return 200 as soon as the process is up.

    ``llm_configured`` tells whether a Gemini key is present, without calling
    the model, so the probe stays fast and free.
    """
    return HealthResponse(status="ok", llm_configured=bool(settings.google_api_key))


@app.post("/ask", response_model=AskResponse, tags=["inference"])
async def ask(request: AskRequest) -> AskResponse:
    """Answer a question about the energy data.

    Stubbed in Phase 0: echoes the question and reports the ``direct`` route.
    Phases 2-3 replace the body with the LangGraph agent.
    """
    logger.info("received question: %s", request.question)
    return AskResponse(
        answer=(
            "L'agent n'est pas encore branché (Phase 0). "
            f"Question reçue : « {request.question} »"
        ),
        route="direct",
        sql=None,
    )
