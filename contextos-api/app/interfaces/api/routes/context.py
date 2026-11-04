"""Context Retrieval API Routes."""

from fastapi import APIRouter, Depends
from app.application.context_retrieval.retrieval_service import (
    ContextRetrievalService,
    RetrievedContextResponse,
)
from app.interfaces.api.dependencies import get_retrieval_service
from app.interfaces.api.schemas.api_schemas import ContextQueryRequest

router = APIRouter(prefix="/context", tags=["Context"])


@router.post("/query", response_model=RetrievedContextResponse)
async def query_context(
    req: ContextQueryRequest,
    retrieval_service: ContextRetrievalService = Depends(get_retrieval_service),
):
    return await retrieval_service.query_context(
        query=req.query,
        top_k=req.top_k,
        asset_types=req.asset_types,
        minimum_confidence=req.minimum_confidence,
        include_lineage_depth=req.include_lineage_depth,
    )

