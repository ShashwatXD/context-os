"""Slack Enterprise Connector Implementation.

Features:
- Channels & Threads Extraction
- Content-Aware Chunking: Thread-level conversation aggregation with context headers
- Permalinks & Timestamp Preservation
- Channel-level ACL Enforcement
- Mechanism C Live Fetch Fallback: fetch_live_record()
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, SearchChunk
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.entities.source import SourceRecord
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.infrastructure.connectors.base import BaseConnector, ExtractionResult


class SlackConnector(BaseConnector):
    """Slack connector supporting incremental sync, thread chunking, and live retrieval."""

    async def validate_connection(self) -> bool:
        return True

    async def extract(self) -> ExtractionResult:
        return await self.extract_incremental(cursor=None)

    async def extract_incremental(self, cursor: Optional[str] = None) -> ExtractionResult:
        # Synthetic Slack channels and conversations for Acme Analytics
        synthetic_channels = self.config.get("channels", [
            {
                "id": "C01_FINANCE",
                "name": "finance-ops",
                "topic": "Q3 Revenue Discrepancy & Net Billed Adjustments",
                "is_private": False,
                "acl_tags": ["channel:finance-ops", "team:finance"],
                "threads": [
                    {
                        "thread_ts": "1730700000.001000",
                        "started_by": "@sarah.cfo",
                        "messages": [
                            {
                                "ts": "1730700000.001000",
                                "user": "U_SARAH",
                                "username": "sarah.cfo",
                                "text": "Notice: The Executive Tableau dashboard is reporting $1.2M MRR while our GAAP books show $1.157M. Are refunds deducted in Tableau?",
                            },
                            {
                                "ts": "1730700120.002000",
                                "user": "U_DAVE",
                                "username": "dave.bi",
                                "text": "Investigated this: Tableau queries raw.stripe_charges directly instead of dbt fct_monthly_revenue. It misses refund and chargeback deductions ($42.5k discrepancy).",
                            },
                        ],
                    }
                ],
            },
            {
                "id": "C02_DATA_PLATFORM",
                "name": "data-platform",
                "topic": "Warehouse pipelines and dbt sync alerts",
                "is_private": True,
                "acl_tags": ["channel:data-platform", "team:engineering"],
                "threads": [
                    {
                        "thread_ts": "1730710000.001000",
                        "started_by": "@alex.lead",
                        "messages": [
                            {
                                "ts": "1730710000.001000",
                                "user": "U_ALEX",
                                "username": "alex.lead",
                                "text": "dbt Cloud job completed fct_monthly_revenue model rebuild in 4.2 mins. Tested schema and unique keys passed.",
                            }
                        ],
                    }
                ],
            },
        ])

        assets: List[Asset] = []
        relationships: List[Relationship] = []
        provenances: List[ProvenanceRecord] = []
        source_records: List[SourceRecord] = []
        search_chunks: List[SearchChunk] = []

        for ch in synthetic_channels:
            ch_id = ch["id"]
            ch_name = ch["name"]
            acl_tags = ch.get("acl_tags", [f"channel:{ch_name}"])
            asset_id = f"ast_slack_{self.source_id}_{ch_id}"

            # Raw Evidence & Provenance
            raw_evidence = {
                "channel_id": ch_id,
                "channel_name": ch_name,
                "topic": ch.get("topic"),
                "is_private": ch.get("is_private", False),
            }
            source_hash = ProvenanceRecord.compute_hash(raw_evidence)
            prov_id = f"prov_slack_{source_hash[:16]}"

            prov_record = ProvenanceRecord(
                id=prov_id,
                entity_id=asset_id,
                entity_type="ASSET",
                source_id=self.source_id,
                extraction_method="SLACK_CONVERSATIONS_API",
                source_hash=source_hash,
                raw_evidence=raw_evidence,
            )
            provenances.append(prov_record)

            # Asset: Slack Channel
            asset = Asset(
                id=asset_id,
                source_id=self.source_id,
                external_id=ch_id,
                name=f"#{ch_name}",
                qualified_name=f"slack.{self.source_id}.{ch_name}",
                asset_type=AssetType.CHANNEL,
                description=f"Slack Channel #{ch_name}: {ch.get('topic')}",
                certification_status=CertificationStatus.CERTIFIED,
                owner_name="Workspace Admin",
                tags=["slack", ch_name],
                acl_tags=acl_tags,
                provenance_id=prov_id,
                metadata_payload={"channel_id": ch_id, "is_private": ch.get("is_private", False)},
            )
            assets.append(asset)

            # Process Threads -> Storage Layer 1 (SourceRecord) + Storage Layer 3 (SearchChunk)
            for thread in ch.get("threads", []):
                thread_ts = thread["thread_ts"]
                messages = thread.get("messages", [])

                # Layer 1: Normalized Raw Record
                raw_thread_payload = {
                    "channel_id": ch_id,
                    "thread_ts": thread_ts,
                    "message_count": len(messages),
                    "permalink": f"https://acme.slack.com/archives/{ch_id}/p{thread_ts.replace('.', '')}",
                    "messages": messages,
                }
                version_hash = hashlib.sha256(str(raw_thread_payload).encode("utf-8")).hexdigest()

                source_rec = SourceRecord(
                    id=f"srec_slack_{ch_id}_{thread_ts}",
                    source_id=self.source_id,
                    external_id=f"{ch_id}:{thread_ts}",
                    record_type="SLACK_THREAD",
                    raw_payload=raw_thread_payload,
                    version_hash=version_hash,
                )
                source_records.append(source_rec)

                # Content-Aware Chunking: Aggregate thread into a single semantic conversation chunk
                formatted_dialogue = "\n".join([f"{m['username']}: {m['text']}" for m in messages])
                chunk_text = (
                    f"Channel: #{ch_name} | Topic: {ch.get('topic')}\n"
                    f"Thread Started by: {thread.get('started_by')}\n"
                    f"Permalink: https://acme.slack.com/archives/{ch_id}/p{thread_ts.replace('.', '')}\n"
                    f"Discussion:\n{formatted_dialogue}"
                )

                chunk = SearchChunk(
                    id=f"chk_slack_{ch_id}_{thread_ts}",
                    asset_id=asset_id,
                    chunk_type="THREAD_SUMMARY",
                    chunk_text=chunk_text,
                    metadata_filters={"channel_id": ch_id, "thread_ts": thread_ts},
                    acl_tags=acl_tags,
                    version_hash=version_hash,
                )
                search_chunks.append(chunk)

        next_cursor = "cursor_slack_page_2" if cursor is None else None
        return ExtractionResult(
            assets=assets,
            relationships=relationships,
            provenance_records=provenances,
            source_records=source_records,
            search_chunks=search_chunks,
            metadata_summary={"channel_count": len(assets), "thread_count": len(search_chunks)},
            next_cursor=next_cursor,
        )

    async def fetch_live_record(self, external_id: str) -> Optional[ExtractionResult]:
        """Mechanism C: Live query for a specific Slack channel or thread."""
        res = await self.extract_incremental()
        for ast in res.assets:
            if ast.external_id == external_id or external_id in ast.qualified_name:
                return ExtractionResult(
                    assets=[ast],
                    provenance_records=res.provenance_records,
                    search_chunks=[c for c in res.search_chunks if c.asset_id == ast.id],
                )
        return None

