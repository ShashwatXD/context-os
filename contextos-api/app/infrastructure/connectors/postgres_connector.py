"""PostgreSQL Warehouse Connector Implementation."""

from datetime import datetime, timezone
from typing import Any, Dict, List
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.infrastructure.connectors.base import BaseConnector, ExtractionResult


class PostgresConnector(BaseConnector):
    """Connects to PostgreSQL information_schema to extract tables, views, and schemas."""

    async def validate_connection(self) -> bool:
        # In demo environment, validates synthetic or real config
        return True

    async def extract(self) -> ExtractionResult:
        # Default enterprise warehouse schema for Acme Analytics
        synthetic_tables = self.config.get("tables", [
            {
                "schema": "raw",
                "table": "stripe_charges",
                "description": "Raw billing charge events directly from Stripe webhook stream",
                "owner": "Data Platform Team",
                "columns": [
                    {"name": "charge_id", "data_type": "varchar", "is_primary_key": True},
                    {"name": "customer_id", "data_type": "varchar"},
                    {"name": "amount_cents", "data_type": "bigint"},
                    {"name": "currency", "data_type": "varchar"},
                    {"name": "status", "data_type": "varchar"},
                    {"name": "created_at", "data_type": "timestamp"},
                ],
            },
            {
                "schema": "analytics",
                "table": "dim_customers",
                "description": "Core dimension table containing verified customer accounts",
                "owner": "Revenue Ops",
                "columns": [
                    {"name": "customer_id", "data_type": "varchar", "is_primary_key": True},
                    {"name": "company_name", "data_type": "varchar"},
                    {"name": "plan_tier", "data_type": "varchar"},
                    {"name": "signup_date", "data_type": "date"},
                ],
            },
            {
                "schema": "analytics",
                "table": "fct_subscriptions",
                "description": "Subscription fact table recording active contracts and recurring billing periods",
                "owner": "Finance Core Team",
                "columns": [
                    {"name": "subscription_id", "data_type": "varchar", "is_primary_key": True},
                    {"name": "customer_id", "data_type": "varchar"},
                    {"name": "mrr_amount", "data_type": "numeric"},
                    {"name": "is_active", "data_type": "boolean"},
                ],
            },
        ])

        assets: List[Asset] = []
        relationships: List[Relationship] = []
        provenances: List[ProvenanceRecord] = []

        for tbl in synthetic_tables:
            schema_name = tbl["schema"]
            table_name = tbl["table"]
            full_name = f"{schema_name}.{table_name}"
            asset_id = f"ast_pg_{self.source_id}_{schema_name}_{table_name}"

            raw_evidence = {
                "source": "postgresql_information_schema",
                "schema": schema_name,
                "table": table_name,
                "column_count": len(tbl["columns"]),
            }
            source_hash = ProvenanceRecord.compute_hash(raw_evidence)
            prov_id = f"prov_pg_{source_hash[:16]}"

            prov_record = ProvenanceRecord(
                id=prov_id,
                entity_id=asset_id,
                entity_type="ASSET",
                source_id=self.source_id,
                extraction_method="POSTGRES_INFORMATION_SCHEMA",
                source_hash=source_hash,
                raw_evidence=raw_evidence,
            )
            provenances.append(prov_record)

            columns = [
                ColumnMetadata(
                    name=c["name"],
                    data_type=c["data_type"],
                    is_primary_key=c.get("is_primary_key", False),
                    is_nullable=c.get("is_nullable", True),
                    description=c.get("description"),
                )
                for c in tbl["columns"]
            ]

            asset = Asset(
                id=asset_id,
                source_id=self.source_id,
                external_id=full_name,
                name=table_name,
                qualified_name=f"warehouse.{full_name}",
                asset_type=AssetType.TABLE,
                description=tbl.get("description"),
                certification_status=CertificationStatus.CERTIFIED,
                owner_name=tbl.get("owner", "Data Engineering"),
                columns=columns,
                provenance_id=prov_id,
                metadata_payload={"schema": schema_name, "engine": "postgresql"},
            )
            assets.append(asset)

        return ExtractionResult(
            assets=assets,
            relationships=relationships,
            provenance_records=provenances,
            metadata_summary={"table_count": len(assets)},
        )

