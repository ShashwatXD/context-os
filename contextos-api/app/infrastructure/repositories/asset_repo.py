"""Asset Repository Implementation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.infrastructure.database.models import AssetModel


class AssetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, asset: Asset) -> Asset:
        stmt = select(AssetModel).where(
            AssetModel.source_id == asset.source_id,
            AssetModel.external_id == asset.external_id,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        columns_data = [c.model_dump() for c in asset.columns]

        if existing:
            existing.name = asset.name
            existing.qualified_name = asset.qualified_name
            existing.asset_type = asset.asset_type.value
            existing.description = asset.description
            existing.certification_status = asset.certification_status.value
            existing.owner_id = asset.owner_id
            existing.owner_name = asset.owner_name
            existing.columns_payload = columns_data
            existing.tags_payload = asset.tags
            existing.metadata_payload = asset.metadata_payload
            existing.provenance_id = asset.provenance_id
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            asset.id = existing.id
            return asset
        else:
            model = AssetModel(
                id=asset.id,
                source_id=asset.source_id,
                external_id=asset.external_id,
                name=asset.name,
                qualified_name=asset.qualified_name,
                asset_type=asset.asset_type.value,
                description=asset.description,
                certification_status=asset.certification_status.value,
                owner_id=asset.owner_id,
                owner_name=asset.owner_name,
                columns_payload=columns_data,
                tags_payload=asset.tags,
                metadata_payload=asset.metadata_payload,
                provenance_id=asset.provenance_id,
                created_at=asset.created_at,
                updated_at=asset.updated_at,
            )
            self.session.add(model)
            await self.session.flush()
            return asset

    async def get_by_id(self, asset_id: str) -> Optional[Asset]:
        stmt = select(AssetModel).where(AssetModel.id == asset_id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def get_by_source_and_external_id(
        self, source_id: str, external_id: str
    ) -> Optional[Asset]:
        stmt = select(AssetModel).where(
            AssetModel.source_id == source_id,
            AssetModel.external_id == external_id,
        )
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def search_assets(
        self,
        query: Optional[str] = None,
        asset_type: Optional[str] = None,
        certification_status: Optional[str] = None,
        owner_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Asset]:
        stmt = select(AssetModel)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    AssetModel.name.ilike(pattern),
                    AssetModel.qualified_name.ilike(pattern),
                    AssetModel.description.ilike(pattern),
                )
            )
        if asset_type:
            stmt = stmt.where(AssetModel.asset_type == asset_type)
        if certification_status:
            stmt = stmt.where(AssetModel.certification_status == certification_status)
        if owner_name:
            stmt = stmt.where(AssetModel.owner_name.ilike(f"%{owner_name}%"))

        stmt = stmt.order_by(desc(AssetModel.created_at)).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return [self._to_domain(m) for m in res.scalars().all()]

    async def count_assets(self) -> int:
        stmt = select(func.count(AssetModel.id))
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def update_certification(
        self, asset_id: str, status: CertificationStatus
    ) -> Optional[Asset]:
        stmt = select(AssetModel).where(AssetModel.id == asset_id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        model.certification_status = status.value
        model.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._to_domain(model)

    def _to_domain(self, model: AssetModel) -> Asset:
        cols = [
            ColumnMetadata(
                name=c.get("name", ""),
                data_type=c.get("data_type", "string"),
                is_primary_key=c.get("is_primary_key", False),
                is_nullable=c.get("is_nullable", True),
                description=c.get("description"),
            )
            for c in (model.columns_payload or [])
        ]
        return Asset(
            id=model.id,
            source_id=model.source_id,
            external_id=model.external_id,
            name=model.name,
            qualified_name=model.qualified_name,
            asset_type=AssetType(model.asset_type),
            description=model.description,
            certification_status=CertificationStatus(model.certification_status),
            owner_id=model.owner_id,
            owner_name=model.owner_name,
            columns=cols,
            tags=model.tags_payload or [],
            metadata_payload=model.metadata_payload or {},
            provenance_id=model.provenance_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

