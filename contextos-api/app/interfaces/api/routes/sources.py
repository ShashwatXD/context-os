"""Enterprise Sources API Routes."""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.domain.entities.source import Source, SourceType
from app.infrastructure.repositories.source_repo import SourceRepository
from app.application.ingestion.ingestion_service import IngestionService
from app.interfaces.api.dependencies import get_source_repo, get_ingestion_service
from app.interfaces.api.schemas.api_schemas import (
    SourceCreateRequest,
    SourceResponse,
    SyncJobResponse,
)

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("", response_model=List[SourceResponse])
async def list_sources(
    source_type: Optional[str] = None,
    source_repo: SourceRepository = Depends(get_source_repo),
):
    sources = await source_repo.list_sources(source_type=source_type)
    return [
        SourceResponse(
            id=s.id,
            name=s.name,
            source_type=s.source_type.value,
            connection_config=s.connection_config,
            is_active=s.is_active,
            last_sync_at=s.last_sync_at,
            last_sync_status=s.last_sync_status.value if s.last_sync_status else None,
            created_at=s.created_at,
        )
        for s in sources
    ]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    req: SourceCreateRequest,
    source_repo: SourceRepository = Depends(get_source_repo),
):
    try:
        st = SourceType(req.source_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source type '{req.source_type}'. Valid types: {[t.value for t in SourceType]}",
        )

    source = Source(
        id=f"src_{uuid.uuid4().hex[:10]}",
        name=req.name,
        source_type=st,
        connection_config=req.connection_config,
    )
    saved = await source_repo.create(source)
    return SourceResponse(
        id=saved.id,
        name=saved.name,
        source_type=saved.source_type.value,
        connection_config=saved.connection_config,
        is_active=saved.is_active,
        last_sync_at=saved.last_sync_at,
        last_sync_status=saved.last_sync_status.value if saved.last_sync_status else None,
        created_at=saved.created_at,
    )


@router.post("/{source_id}/sync", response_model=SyncJobResponse)
async def trigger_source_sync(
    source_id: str,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    sync_record = await ingestion_service.sync_source(source_id)
    return SyncJobResponse(
        sync_id=sync_record.id,
        source_id=sync_record.source_id,
        status=sync_record.status.value,
        entities_extracted=sync_record.entities_extracted,
        relationships_extracted=sync_record.relationships_extracted,
        error_message=sync_record.error_message,
        started_at=sync_record.started_at,
        completed_at=sync_record.completed_at,
    )


@router.get("/{source_id}/history", response_model=List[SyncJobResponse])
async def get_sync_history(
    source_id: str,
    limit: int = 20,
    source_repo: SourceRepository = Depends(get_source_repo),
):
    history = await source_repo.get_sync_history(source_id=source_id, limit=limit)
    return [
        SyncJobResponse(
            sync_id=h.id,
            source_id=h.source_id,
            status=h.status.value,
            entities_extracted=h.entities_extracted,
            relationships_extracted=h.relationships_extracted,
            error_message=h.error_message,
            started_at=h.started_at,
            completed_at=h.completed_at,
        )
        for h in history
    ]

