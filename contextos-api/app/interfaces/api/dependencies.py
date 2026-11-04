"""FastAPI Dependency Injection Providers."""

from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.session import get_db_session
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.infrastructure.repositories.eval_repo import EvaluationRepository
from app.application.ingestion.ingestion_service import IngestionService
from app.application.entity_resolution.resolver import EntityResolutionService
from app.application.context_retrieval.retrieval_service import ContextRetrievalService
from app.application.enrichment.enrichment_service import EnrichmentService
from app.application.approvals.approval_service import ApprovalService
from app.application.agent_execution.runner import AgentRunner
from app.application.evaluation.eval_service import EvaluationService


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_db_session():
        yield s


def get_source_repo(session: AsyncSession = Depends(get_session)) -> SourceRepository:
    return SourceRepository(session)


def get_asset_repo(session: AsyncSession = Depends(get_session)) -> AssetRepository:
    return AssetRepository(session)


def get_relationship_repo(session: AsyncSession = Depends(get_session)) -> RelationshipRepository:
    return RelationshipRepository(session)


def get_approval_repo(session: AsyncSession = Depends(get_session)) -> ApprovalRepository:
    return ApprovalRepository(session)


def get_trace_repo(session: AsyncSession = Depends(get_session)) -> TraceRepository:
    return TraceRepository(session)


def get_eval_repo(session: AsyncSession = Depends(get_session)) -> EvaluationRepository:
    return EvaluationRepository(session)


def get_ingestion_service(session: AsyncSession = Depends(get_session)) -> IngestionService:
    return IngestionService(session)


def get_resolution_service(session: AsyncSession = Depends(get_session)) -> EntityResolutionService:
    return EntityResolutionService(session)


def get_retrieval_service(session: AsyncSession = Depends(get_session)) -> ContextRetrievalService:
    return ContextRetrievalService(session)


def get_enrichment_service(session: AsyncSession = Depends(get_session)) -> EnrichmentService:
    return EnrichmentService(session)


def get_approval_service(session: AsyncSession = Depends(get_session)) -> ApprovalService:
    return ApprovalService(session)


def get_agent_runner(session: AsyncSession = Depends(get_session)) -> AgentRunner:
    return AgentRunner(session)


def get_evaluation_service(session: AsyncSession = Depends(get_session)) -> EvaluationService:
    return EvaluationService(session)

