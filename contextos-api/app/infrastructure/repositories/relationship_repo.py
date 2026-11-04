"""Relationship Repository & Multi-Hop Lineage Graph Traversal."""

from typing import Any, Dict, List, Optional, Set
from collections import deque
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.infrastructure.database.models import RelationshipModel, AssetModel


class RelationshipRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, rel: Relationship) -> Relationship:
        stmt = select(RelationshipModel).where(
            RelationshipModel.source_asset_id == rel.source_asset_id,
            RelationshipModel.target_asset_id == rel.target_asset_id,
            RelationshipModel.relationship_type == rel.relationship_type.value,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.confidence = rel.confidence
            existing.provenance_id = rel.provenance_id
            existing.properties_payload = rel.properties
            await self.session.flush()
            rel.id = existing.id
            return rel

        model = RelationshipModel(
            id=rel.id,
            source_asset_id=rel.source_asset_id,
            target_asset_id=rel.target_asset_id,
            relationship_type=rel.relationship_type.value,
            confidence=rel.confidence,
            provenance_id=rel.provenance_id,
            properties_payload=rel.properties,
            valid_from=rel.valid_from,
            valid_to=rel.valid_to,
            created_at=rel.created_at,
        )
        self.session.add(model)
        await self.session.flush()
        return rel

    async def list_by_asset(
        self, asset_id: str, direction: str = "both"
    ) -> List[Relationship]:
        stmt = select(RelationshipModel)
        if direction == "outbound":
            stmt = stmt.where(RelationshipModel.source_asset_id == asset_id)
        elif direction == "inbound":
            stmt = stmt.where(RelationshipModel.target_asset_id == asset_id)
        else:
            stmt = stmt.where(
                or_(
                    RelationshipModel.source_asset_id == asset_id,
                    RelationshipModel.target_asset_id == asset_id,
                )
            )
        res = await self.session.execute(stmt)
        return [self._to_domain(m) for m in res.scalars().all()]

    async def list_all(self, limit: int = 200) -> List[Relationship]:
        stmt = select(RelationshipModel).limit(limit)
        res = await self.session.execute(stmt)
        return [self._to_domain(m) for m in res.scalars().all()]

    async def get_lineage(
        self, asset_id: str, depth: int = 3, direction: str = "both"
    ) -> Dict[str, Any]:
        """Traverses the directed lineage graph up to `depth` hops.

        Direction:
        - "upstream": traces sources that feed into this asset (e.g. source tables -> models)
        - "downstream": traces consumers of this asset (e.g. models -> dashboards)
        - "both": traces both directions
        """
        visited_nodes: Set[str] = {asset_id}
        discovered_edges: List[Dict[str, Any]] = []
        queue = deque([(asset_id, 0)])

        while queue:
            curr_id, curr_depth = queue.popleft()
            if curr_depth >= depth:
                continue

            # Find matching edges
            conditions = []
            if direction in ("downstream", "both"):
                # Outbound: curr_id is source
                conditions.append(RelationshipModel.source_asset_id == curr_id)
            if direction in ("upstream", "both"):
                # Inbound: curr_id is target
                conditions.append(RelationshipModel.target_asset_id == curr_id)

            if not conditions:
                continue

            stmt = select(RelationshipModel).where(or_(*conditions))
            res = await self.session.execute(stmt)
            rels = res.scalars().all()

            for r in rels:
                edge_dict = {
                    "id": r.id,
                    "source": r.source_asset_id,
                    "target": r.target_asset_id,
                    "relationship_type": r.relationship_type,
                    "confidence": r.confidence,
                    "provenance_id": r.provenance_id,
                }
                if edge_dict not in discovered_edges:
                    discovered_edges.append(edge_dict)

                next_node = (
                    r.target_asset_id if r.source_asset_id == curr_id else r.source_asset_id
                )
                if next_node not in visited_nodes:
                    visited_nodes.add(next_node)
                    queue.append((next_node, curr_depth + 1))

        # Fetch asset details for all visited nodes
        ast_stmt = select(AssetModel).where(AssetModel.id.in_(list(visited_nodes)))
        ast_res = await self.session.execute(ast_stmt)
        node_models = ast_res.scalars().all()

        nodes = [
            {
                "id": n.id,
                "name": n.name,
                "qualified_name": n.qualified_name,
                "asset_type": n.asset_type,
                "certification_status": n.certification_status,
                "owner_name": n.owner_name,
            }
            for n in node_models
        ]

        return {
            "root_asset_id": asset_id,
            "depth": depth,
            "direction": direction,
            "nodes": nodes,
            "edges": discovered_edges,
        }

    def _to_domain(self, model: RelationshipModel) -> Relationship:
        return Relationship(
            id=model.id,
            source_asset_id=model.source_asset_id,
            target_asset_id=model.target_asset_id,
            relationship_type=RelationshipType(model.relationship_type),
            confidence=model.confidence,
            provenance_id=model.provenance_id,
            properties=model.properties_payload or {},
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            created_at=model.created_at,
        )

