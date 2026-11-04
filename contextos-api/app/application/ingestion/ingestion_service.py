"""Ingestion Service: Orchestrates source connectors, extraction, provenance, and persistence."""

from datetime import datetime, timezone
import uuid
from typing import Dict, Optional, Type
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConnectorError, EntityNotFoundError
from app.domain.entities.source import Source, SourceType, SyncRecord, SyncStatus
from app.infrastructure.connectors.base import BaseConnector, ExtractionResult
from app.infrastructure.connectors.postgres_connector import PostgresConnector
from app.infrastructure.connectors.dbt_connector import DbtConnector
from app.infrastructure.connectors.notion_connector import NotionConnector
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository

CONNECTOR_REGISTRY: Dict[SourceType, Type[BaseConnector]] = {
    SourceType.POSTGRESQL: PostgresConnector,
    SourceType.SNOWFLAKE: PostgresConnector,  # Snowflake uses compatible DDL extractor
    SourceType.DBT: DbtConnector,
    SourceType.NOTION: NotionConnector,
    SourceType.GITHUB: NotionConnector,       # GitHub doc extractor
}


class IngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.source_repo = SourceRepository(session)
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.provenance_repo = ProvenanceRepository(session)

    async def sync_source(self, source_id: str) -> SyncRecord:
        source = await self.source_repo.get_by_id(source_id)
        if not source:
            raise EntityNotFoundError("Source", source_id)

        connector_cls = CONNECTOR_REGISTRY.get(source.source_type)
        if not connector_cls:
            raise ConnectorError(source_id, f"No connector registered for {source.source_type}")

        connector = connector_cls(source_id=source.id, connection_config=source.connection_config)

        sync_id = f"sync_{uuid.uuid4().hex[:12]}"
        sync_record = SyncRecord(
            id=sync_id,
            source_id=source_id,
            status=SyncStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        await self.source_repo.create_sync_record(sync_record)

        try:
            # 1. Connection check
            is_valid = await connector.validate_connection()
            if not is_valid:
                raise ConnectorError(source_id, "Source connection validation failed")

            # 2. Extract metadata & provenance
            result: ExtractionResult = await connector.extract()

            # 3. Persist provenance records
            for prov in result.provenance_records:
                await self.provenance_repo.create(prov)

            # 4. Upsert assets
            name_to_id_map: Dict[str, str] = {}
            for asset in result.assets:
                saved = await self.asset_repo.upsert(asset)
                name_to_id_map[asset.name] = saved.id
                name_to_id_map[asset.external_id] = saved.id

            # 5. Persist relationships (resolving any external or partial names)
            persisted_rel_count = 0
            for rel in result.relationships:
                # Resolve source asset ID if passed as external reference
                resolved_source = name_to_id_map.get(rel.source_asset_id, rel.source_asset_id)
                # Check if asset exists in DB if not in map
                if resolved_source not in name_to_id_map.values():
                    existing = await self.asset_repo.get_by_source_and_external_id(
                        source_id, rel.source_asset_id
                    )
                    if existing:
                        resolved_source = existing.id

                # Resolve target asset ID
                resolved_target = name_to_id_map.get(rel.target_asset_id, rel.target_asset_id)

                if resolved_source != resolved_target:
                    rel.source_asset_id = resolved_source
                    rel.target_asset_id = resolved_target
                    try:
                        await self.relationship_repo.create(rel)
                        persisted_rel_count += 1
                    except Exception:
                        pass  # Ignore invalid or missing targets during incremental sync

            # 6. Complete Sync Record
            sync_record.status = SyncStatus.COMPLETED
            sync_record.entities_extracted = len(result.assets)
            sync_record.relationships_extracted = persisted_rel_count
            sync_record.completed_at = datetime.now(timezone.utc)
            await self.source_repo.update_sync_record(sync_record)

            return sync_record

        except Exception as exc:
            sync_record.status = SyncStatus.FAILED
            sync_record.error_message = str(exc)
            sync_record.completed_at = datetime.now(timezone.utc)
            await self.source_repo.update_sync_record(sync_record)
            raise

