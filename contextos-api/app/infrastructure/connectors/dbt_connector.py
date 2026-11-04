"""dbt Transformation Metadata Connector Implementation."""

from typing import Any, Dict, List
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.infrastructure.connectors.base import BaseConnector, ExtractionResult


class DbtConnector(BaseConnector):
    """Parses dbt manifest.json / catalog metadata to extract models and DAG lineage."""

    async def validate_connection(self) -> bool:
        return True

    async def extract(self) -> ExtractionResult:
        # Synthetic dbt project models for Acme Analytics
        synthetic_models = self.config.get("models", [
            {
                "unique_id": "model.acme_analytics.stg_stripe_charges",
                "name": "stg_stripe_charges",
                "description": "Standardized staging model for Stripe charges with currency normalization",
                "owner": "Data Platform Team",
                "upstream_sources": ["raw.stripe_charges"],
                "columns": [
                    {"name": "charge_id", "data_type": "varchar", "description": "Primary key"},
                    {"name": "amount_usd", "data_type": "numeric", "description": "Normalized USD amount"},
                ],
            },
            {
                "unique_id": "model.acme_analytics.fct_monthly_revenue",
                "name": "fct_monthly_revenue",
                "description": "Official company Monthly Recurring Revenue (MRR) transformation model incorporating refunds and cancellations",
                "owner": "Finance Core Team",
                "upstream_sources": ["stg_stripe_charges", "analytics.fct_subscriptions"],
                "columns": [
                    {"name": "revenue_month", "data_type": "date"},
                    {"name": "gross_revenue", "data_type": "numeric"},
                    {"name": "net_revenue", "data_type": "numeric"},
                    {"name": "refunds_amount", "data_type": "numeric"},
                ],
            },
        ])

        assets: List[Asset] = []
        relationships: List[Relationship] = []
        provenances: List[ProvenanceRecord] = []

        for m in synthetic_models:
            model_name = m["name"]
            asset_id = f"ast_dbt_{self.source_id}_{model_name}"

            raw_evidence = {
                "dbt_unique_id": m["unique_id"],
                "model_name": model_name,
                "upstream_sources": m["upstream_sources"],
            }
            source_hash = ProvenanceRecord.compute_hash(raw_evidence)
            prov_id = f"prov_dbt_{source_hash[:16]}"

            prov_record = ProvenanceRecord(
                id=prov_id,
                entity_id=asset_id,
                entity_type="ASSET",
                source_id=self.source_id,
                extraction_method="DBT_MANIFEST_PARSER",
                source_hash=source_hash,
                raw_evidence=raw_evidence,
            )
            provenances.append(prov_record)

            columns = [
                ColumnMetadata(
                    name=c["name"],
                    data_type=c["data_type"],
                    description=c.get("description"),
                )
                for c in m["columns"]
            ]

            asset = Asset(
                id=asset_id,
                source_id=self.source_id,
                external_id=m["unique_id"],
                name=model_name,
                qualified_name=f"dbt.acme_analytics.{model_name}",
                asset_type=AssetType.TRANSFORMATION_MODEL,
                description=m["description"],
                certification_status=CertificationStatus.CERTIFIED,
                owner_name=m["owner"],
                columns=columns,
                provenance_id=prov_id,
                metadata_payload={"dbt_unique_id": m["unique_id"]},
            )
            assets.append(asset)

            # Store upstream references to link during ingestion
            for upstream in m.get("upstream_sources", []):
                rel_id = f"rel_dbt_{model_name}_{upstream.replace('.', '_')}"
                rel = Relationship(
                    id=rel_id,
                    source_asset_id=upstream,  # Will be resolved to asset ID in ingestion/resolution
                    target_asset_id=asset_id,
                    relationship_type=RelationshipType.TRANSFORMS_TO,
                    confidence=1.0,
                    provenance_id=prov_id,
                    properties={"dbt_lineage": True},
                )
                relationships.append(rel)

        return ExtractionResult(
            assets=assets,
            relationships=relationships,
            provenance_records=provenances,
            metadata_summary={"dbt_model_count": len(assets)},
        )

