"""Pytest configuration and shared async fixtures for ContextOS."""

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.infrastructure.database.models import Base
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.infrastructure.repositories.eval_repo import EvaluationRepository


@pytest_asyncio.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a fresh, isolated in-memory SQLite database session for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def asset_repo(test_session: AsyncSession) -> AssetRepository:
    return AssetRepository(test_session)


@pytest_asyncio.fixture
async def source_repo(test_session: AsyncSession) -> SourceRepository:
    return SourceRepository(test_session)


@pytest_asyncio.fixture
async def relationship_repo(test_session: AsyncSession) -> RelationshipRepository:
    return RelationshipRepository(test_session)


@pytest_asyncio.fixture
async def provenance_repo(test_session: AsyncSession) -> ProvenanceRepository:
    return ProvenanceRepository(test_session)


@pytest_asyncio.fixture
async def approval_repo(test_session: AsyncSession) -> ApprovalRepository:
    return ApprovalRepository(test_session)


@pytest_asyncio.fixture
async def trace_repo(test_session: AsyncSession) -> TraceRepository:
    return TraceRepository(test_session)


@pytest_asyncio.fixture
async def eval_repo(test_session: AsyncSession) -> EvaluationRepository:
    return EvaluationRepository(test_session)

