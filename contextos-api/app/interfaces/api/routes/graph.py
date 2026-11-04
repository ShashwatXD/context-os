"""Context Graph Exploration API Routes."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.interfaces.api.dependencies import get_relationship_repo, get_asset_repo

router = APIRouter(prefix="/graph", tags=["Graph"])


@router.get("")
async def get_context_graph(
    limit: int = 100,
    relationship_repo: RelationshipRepository = Depends(get_relationship_repo),
    asset_repo: AssetRepository = Depends(get_asset_repo),
) -> Dict[str, Any]:
    rels = await relationship_repo.list_all(limit=limit)
    asset_ids = set()
    edges = []
    for r in rels:
        asset_ids.add(r.source_asset_id)
        asset_ids.add(r.target_asset_id)
        edges.append({
            "id": r.id,
            "source": r.source_asset_id,
            "target": r.target_asset_id,
            "type": r.relationship_type.value,
            "confidence": r.confidence,
        })

    nodes = []
    for aid in asset_ids:
        ast = await asset_repo.get_by_id(aid)
        if ast:
            nodes.append({
                "id": ast.id,
                "name": ast.name,
                "qualified_name": ast.qualified_name,
                "asset_type": ast.asset_type.value,
                "certification_status": ast.certification_status.value,
                "owner_name": ast.owner_name,
            })

    return {"nodes": nodes, "edges": edges}

