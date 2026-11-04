"""Notion / Documentation Connector Implementation."""

from typing import Any, Dict, List
from app.domain.entities.asset import Asset, AssetType, CertificationStatus
from app.domain.entities.provenance import ProvenanceRecord
from app.infrastructure.connectors.base import BaseConnector, ExtractionResult


class NotionConnector(BaseConnector):
    """Extracts business glossary terms, metric definitions, and policy documents."""

    async def validate_connection(self) -> bool:
        return True

    async def extract(self) -> ExtractionResult:
        # Synthetic Notion business glossary documents for Acme Analytics
        synthetic_docs = self.config.get("documents", [
            {
                "doc_id": "notion_finance_policy_mrr",
                "title": "Monthly Recurring Revenue (MRR) - Official Finance Policy",
                "owner": "Finance Core Team",
                "asset_type": AssetType.METRIC,
                "content": (
                    "Section 4.1: Monthly Recurring Revenue (MRR) is defined strictly as normalized "
                    "subscription revenue recognized within a calendar month. It EXCLUDES one-time setup fees "
                    "and MUST deduct processed churn, mid-month downgrades, and chargebacks."
                ),
                "certification_status": CertificationStatus.CERTIFIED,
            },
            {
                "doc_id": "notion_sales_commission_policy",
                "title": "Monthly Billed Revenue (Sales Definition)",
                "owner": "Sales Operations",
                "asset_type": AssetType.DOCUMENTATION,
                "content": (
                    "Sales compensation evaluates gross billed invoices issued in the month, "
                    "regardless of refund status or multi-month advance collection periods."
                ),
                "certification_status": CertificationStatus.DISPUTED,
            },
        ])

        assets: List[Asset] = []
        provenances: List[ProvenanceRecord] = []

        for doc in synthetic_docs:
            asset_id = f"ast_notion_{self.source_id}_{doc['doc_id']}"

            raw_evidence = {
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "content": doc["content"],
            }
            source_hash = ProvenanceRecord.compute_hash(raw_evidence)
            prov_id = f"prov_notion_{source_hash[:16]}"

            prov_record = ProvenanceRecord(
                id=prov_id,
                entity_id=asset_id,
                entity_type="ASSET",
                source_id=self.source_id,
                extraction_method="NOTION_PAGE_EXTRACTOR",
                source_hash=source_hash,
                raw_evidence=raw_evidence,
            )
            provenances.append(prov_record)

            asset = Asset(
                id=asset_id,
                source_id=self.source_id,
                external_id=doc["doc_id"],
                name=doc["title"],
                qualified_name=f"notion.finance.{doc['doc_id']}",
                asset_type=doc.get("asset_type", AssetType.DOCUMENTATION),
                description=doc["content"],
                certification_status=doc.get("certification_status", CertificationStatus.CERTIFIED),
                owner_name=doc["owner"],
                provenance_id=prov_id,
                metadata_payload={"page_id": doc["doc_id"]},
            )
            assets.append(asset)

        return ExtractionResult(
            assets=assets,
            relationships=[],
            provenance_records=provenances,
            metadata_summary={"document_count": len(assets)},
        )

