"""Source & Sync Record Repository Implementation."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.source import (
    DeadLetterRecord,
    Source,
    SourceRecord,
    SourceType,
    SyncCheckpoint,
    SyncRecord,
    SyncStatus,
)
from app.infrastructure.database.models import (
    DeadLetterRecordModel,
    SourceModel,
    SourceRecordModel,
    SyncCheckpointModel,
    SyncRecordModel,
)


class SourceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, source: Source) -> Source:
        model = SourceModel(
            id=source.id,
            name=source.name,
            source_type=source.source_type.value,
            connection_config=source.connection_config,
            is_active=source.is_active,
            freshness_threshold_seconds=source.freshness_threshold_seconds,
            auth_type=source.auth_type,
            oauth_scopes=source.oauth_scopes,
            last_sync_at=source.last_sync_at,
            last_sync_status=source.last_sync_status.value if source.last_sync_status else None,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
        self.session.add(model)
        await self.session.flush()
        return source

    async def get_by_id(self, source_id: str) -> Optional[Source]:
        stmt = select(SourceModel).where(SourceModel.id == source_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def list_sources(self, source_type: Optional[str] = None) -> List[Source]:
        stmt = select(SourceModel)
        if source_type:
            stmt = stmt.where(SourceModel.source_type == source_type)
        stmt = stmt.order_by(desc(SourceModel.created_at))
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def create_sync_record(self, record: SyncRecord) -> SyncRecord:
        model = SyncRecordModel(
            id=record.id,
            source_id=record.source_id,
            status=record.status.value,
            entities_extracted=record.entities_extracted,
            relationships_extracted=record.relationships_extracted,
            error_message=record.error_message,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )
        self.session.add(model)
        await self.session.flush()
        return record

    async def update_sync_record(self, record: SyncRecord) -> SyncRecord:
        stmt = select(SyncRecordModel).where(SyncRecordModel.id == record.id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model:
            model.status = record.status.value
            model.entities_extracted = record.entities_extracted
            model.relationships_extracted = record.relationships_extracted
            model.error_message = record.error_message
            model.completed_at = record.completed_at
            await self.session.flush()

            # Also update parent source last_sync
            src_stmt = select(SourceModel).where(SourceModel.id == record.source_id)
            src_res = await self.session.execute(src_stmt)
            src_model = src_res.scalar_one_or_none()
            if src_model:
                src_model.last_sync_at = record.completed_at or datetime.now(timezone.utc)
                src_model.last_sync_status = record.status.value
                await self.session.flush()
        return record

    async def get_sync_history(self, source_id: str, limit: int = 20) -> List[SyncRecord]:
        stmt = (
            select(SyncRecordModel)
            .where(SyncRecordModel.source_id == source_id)
            .order_by(desc(SyncRecordModel.started_at))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [
            SyncRecord(
                id=m.id,
                source_id=m.source_id,
                status=SyncStatus(m.status),
                entities_extracted=m.entities_extracted,
                relationships_extracted=m.relationships_extracted,
                error_message=m.error_message,
                started_at=m.started_at,
                completed_at=m.completed_at,
            )
            for m in res.scalars().all()
        ]

    def _to_domain(self, model: SourceModel) -> Source:
        return Source(
            id=model.id,
            name=model.name,
            source_type=SourceType(model.source_type),
            connection_config=model.connection_config,
            is_active=model.is_active,
            freshness_threshold_seconds=getattr(model, "freshness_threshold_seconds", 900),
            auth_type=getattr(model, "auth_type", "API_TOKEN"),
            oauth_scopes=getattr(model, "oauth_scopes", []) or [],
            last_sync_at=model.last_sync_at,
            last_sync_status=SyncStatus(model.last_sync_status) if model.last_sync_status else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # Checkpoint Persistence
    async def save_checkpoint(self, checkpoint: SyncCheckpoint) -> SyncCheckpoint:
        stmt = select(SyncCheckpointModel).where(SyncCheckpointModel.source_id == checkpoint.source_id)
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.cursor_value = checkpoint.cursor_value
            existing.checkpoint_metadata = checkpoint.checkpoint_metadata
            existing.updated_at = datetime.now(timezone.utc)
            checkpoint.id = existing.id
        else:
            model = SyncCheckpointModel(
                id=checkpoint.id,
                source_id=checkpoint.source_id,
                cursor_value=checkpoint.cursor_value,
                checkpoint_metadata=checkpoint.checkpoint_metadata,
                updated_at=checkpoint.updated_at,
            )
            self.session.add(model)
        await self.session.flush()
        return checkpoint

    async def get_checkpoint(self, source_id: str) -> Optional[SyncCheckpoint]:
        stmt = select(SyncCheckpointModel).where(SyncCheckpointModel.source_id == source_id)
        res = await self.session.execute(stmt)
        m = res.scalar_one_or_none()
        if not m:
            return None
        return SyncCheckpoint(
            id=m.id,
            source_id=m.source_id,
            cursor_value=m.cursor_value,
            checkpoint_metadata=m.checkpoint_metadata or {},
            updated_at=m.updated_at,
        )

    # Dead-Letter Queue (DLQ)
    async def record_dead_letter(self, dlq: DeadLetterRecord) -> DeadLetterRecord:
        model = DeadLetterRecordModel(
            id=dlq.id,
            source_id=dlq.source_id,
            raw_record_id=dlq.raw_record_id,
            payload=dlq.payload,
            error_reason=dlq.error_reason,
            retry_count=dlq.retry_count,
            failed_at=dlq.failed_at,
        )
        self.session.add(model)
        await self.session.flush()
        return dlq

    async def list_dead_letters(
        self, source_id: Optional[str] = None, limit: int = 50
    ) -> List[DeadLetterRecord]:
        stmt = select(DeadLetterRecordModel)
        if source_id:
            stmt = stmt.where(DeadLetterRecordModel.source_id == source_id)
        stmt = stmt.order_by(desc(DeadLetterRecordModel.failed_at)).limit(limit)
        res = await self.session.execute(stmt)
        return [
            DeadLetterRecord(
                id=m.id,
                source_id=m.source_id,
                raw_record_id=m.raw_record_id,
                payload=m.payload or {},
                error_reason=m.error_reason,
                retry_count=m.retry_count,
                failed_at=m.failed_at,
            )
            for m in res.scalars().all()
        ]

    # Layer 1: Normalized Source Records
    async def upsert_source_record(self, record: SourceRecord) -> SourceRecord:
        stmt = select(SourceRecordModel).where(
            SourceRecordModel.source_id == record.source_id,
            SourceRecordModel.external_id == record.external_id,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.raw_payload = record.raw_payload
            existing.version_hash = record.version_hash
            existing.is_deleted = record.is_deleted
            existing.record_type = record.record_type
            record.id = existing.id
        else:
            model = SourceRecordModel(
                id=record.id,
                source_id=record.source_id,
                external_id=record.external_id,
                record_type=record.record_type,
                raw_payload=record.raw_payload,
                version_hash=record.version_hash,
                is_deleted=record.is_deleted,
                ingested_at=record.ingested_at,
            )
            self.session.add(model)
        await self.session.flush()
        return record

    async def mark_source_record_deleted(self, source_id: str, external_id: str) -> bool:
        stmt = select(SourceRecordModel).where(
            SourceRecordModel.source_id == source_id,
            SourceRecordModel.external_id == external_id,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.is_deleted = True
            await self.session.flush()
            return True
        return False

