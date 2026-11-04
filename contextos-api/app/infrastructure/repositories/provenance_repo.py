"""Provenance Repository Implementation."""

from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.provenance import ProvenanceRecord
from app.infrastructure.database.models import ProvenanceRecordModel


class ProvenanceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, record: ProvenanceRecord) -> ProvenanceRecord:
        model = ProvenanceRecordModel(
            id=record.id,
            entity_id=record.entity_id,
            entity_type=record.entity_type,
            source_id=record.source_id,
            extraction_method=record.extraction_method,
            source_hash=record.source_hash,
            raw_evidence_payload=record.raw_evidence,
            captured_at=record.captured_at,
        )
        self.session.add(model)
        await self.session.flush()
        return record

    async def get_by_id(self, record_id: str) -> Optional[ProvenanceRecord]:
        stmt = select(ProvenanceRecordModel).where(ProvenanceRecordModel.id == record_id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_entity(self, entity_id: str) -> List[ProvenanceRecord]:
        stmt = (
            select(ProvenanceRecordModel)
            .where(ProvenanceRecordModel.entity_id == entity_id)
            .order_by(desc(ProvenanceRecordModel.captured_at))
        )
        res = await self.session.execute(stmt)
        return [self._to_domain(m) for m in res.scalars().all()]

    def _to_domain(self, model: ProvenanceRecordModel) -> ProvenanceRecord:
        return ProvenanceRecord(
            id=model.id,
            entity_id=model.entity_id,
            entity_type=model.entity_type,
            source_id=model.source_id,
            extraction_method=model.extraction_method,
            source_hash=model.source_hash,
            raw_evidence=model.raw_evidence_payload or {},
            captured_at=model.captured_at,
        )

