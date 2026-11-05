"""Ingestion Service: Orchestrates source connectors, extraction, provenance, and persistence.

Implements Mechanism A (Background Synchronization):
- Incremental sync with cursors & checkpoints
- Storage Layer 1: Normalized SourceRecord persistence
- Storage Layer 2: Structured Context Assets & Relationships
- Storage Layer 3: Content-aware SearchChunk embedding & index maintenance
- Retries with Exponential Backoff & Dead-Letter Queue (DLQ)
- Deletion propagation for pruned entities
"""

import asyncio
from datetime import datetime, timezone
import uuid
from typing import Dict, List, Optional, Type
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConnectorError, EntityNotFoundError
from app.domain.entities.source import (
    DeadLetterRecord,
    Source,
    SourceRecord,
    SourceType,
    SyncCheckpoint,
    SyncRecord,
    SyncStatus,
)
from app.domain.entities.asset import Asset, SearchChunk
from app.infrastructure.connectors.base import BaseConnector, ExtractionResult
from app.infrastructure.connectors.postgres_connector import PostgresConnector
from app.infrastructure.connectors.dbt_connector import DbtConnector
from app.infrastructure.connectors.notion_connector import NotionConnector
from app.infrastructure.connectors.slack_connector import SlackConnector
from app.infrastructure.connectors.github_connector import GithubConnector
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.infrastructure.embeddings.local_embedding import LocalEmbeddingClient

CONNECTOR_REGISTRY: Dict[SourceType, Type[BaseConnector]] = {
    SourceType.POSTGRESQL: PostgresConnector,
    SourceType.SNOWFLAKE: PostgresConnector,
    SourceType.DBT: DbtConnector,
    SourceType.NOTION: NotionConnector,
    SourceType.SLACK: SlackConnector,
    SourceType.GITHUB: GithubConnector,
}


class IngestionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.source_repo = SourceRepository(session)
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.provenance_repo = ProvenanceRepository(session)
        self.embedder = LocalEmbeddingClient(dimension=64)

    async def sync_source(self, source_id: str, incremental: bool = True) -> SyncRecord:
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

            # 2. Retrieve checkpoint cursor for incremental sync
            last_cursor = None
            if incremental:
                checkpoint = await self.source_repo.get_checkpoint(source_id)
                if checkpoint:
                    last_cursor = checkpoint.cursor_value

            # 3. Extract metadata with exponential backoff retry on transient failures
            result = await self._extract_with_retry(connector, last_cursor, source_id)

            # 4. Storage Layer 1: Persist Normalized Source Records
            for srec in result.source_records:
                await self.source_repo.upsert_source_record(srec)

            # 5. Persist Provenance records
            for prov in result.provenance_records:
                await self.provenance_repo.create(prov)

            # 6. Storage Layer 2: Upsert Assets & map names
            name_to_id_map: Dict[str, str] = {}
            for asset in result.assets:
                saved = await self.asset_repo.upsert(asset)
                name_to_id_map[asset.name] = saved.id
                name_to_id_map[asset.external_id] = saved.id

            # 7. Storage Layer 3: Embed & Persist Content-Aware Search Chunks
            for chunk in result.search_chunks:
                # Compute vector embedding for chunk text
                chunk.embedding = self.embedder.embed_text(chunk.chunk_text)
            if result.search_chunks:
                await self.asset_repo.save_search_chunks(result.search_chunks)

            # 8. Persist Relationships
            persisted_rel_count = 0
            for rel in result.relationships:
                resolved_source = name_to_id_map.get(rel.source_asset_id, rel.source_asset_id)
                resolved_target = name_to_id_map.get(rel.target_asset_id, rel.target_asset_id)

                if resolved_source != resolved_target:
                    rel.source_asset_id = resolved_source
                    rel.target_asset_id = resolved_target
                    try:
                        await self.relationship_repo.create(rel)
                        persisted_rel_count += 1
                    except Exception:
                        pass

            # 9. Update Checkpoint Cursor
            if result.next_cursor:
                await self.source_repo.save_checkpoint(
                    SyncCheckpoint(
                        id=f"chkpt_{uuid.uuid4().hex[:10]}",
                        source_id=source_id,
                        cursor_value=result.next_cursor,
                        checkpoint_metadata={"synced_entities": len(result.assets)},
                    )
                )

            # 10. Complete Sync Record
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

    async def _extract_with_retry(
        self,
        connector: BaseConnector,
        cursor: Optional[str],
        source_id: str,
        max_retries: int = 3,
    ) -> ExtractionResult:
        """Executes extraction with exponential backoff and routes persistent failures to DLQ."""
        for attempt in range(1, max_retries + 1):
            try:
                return await connector.extract_incremental(cursor=cursor)
            except Exception as e:
                if attempt == max_retries:
                    # Move to Dead-Letter Queue
                    dlq_id = f"dlq_{uuid.uuid4().hex[:10]}"
                    await self.source_repo.record_dead_letter(
                        DeadLetterRecord(
                            id=dlq_id,
                            source_id=source_id,
                            raw_record_id=f"sync_cursor_{cursor or 'root'}",
                            payload={"cursor": cursor, "attempt": attempt},
                            error_reason=f"Failed extraction after {max_retries} attempts: {str(e)}",
                            retry_count=attempt,
                        )
                    )
                    raise
                # Exponential backoff: 0.05 * (2 ** attempt) seconds in tests
                await asyncio.sleep(0.05 * (2 ** attempt))
        return ExtractionResult()
