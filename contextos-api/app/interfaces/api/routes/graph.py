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
    all_assets = await asset_repo.search_assets(limit=limit)

    asset_map = {}
    nodes_dict = {}
    for a in all_assets:
        asset_map[a.id] = a
        asset_map[a.qualified_name] = a
        nodes_dict[a.id] = {
            "id": a.id,
            "name": a.name,
            "qualified_name": a.qualified_name,
            "asset_type": a.asset_type.value,
            "certification_status": a.certification_status.value,
            "owner_name": a.owner_name,
        }

    edges = []
    for r in rels:
        src = r.source_asset_id
        tgt = r.target_asset_id

        if src in asset_map:
            src = asset_map[src].id
        elif src not in nodes_dict:
            nodes_dict[src] = {
                "id": src,
                "name": src.split(".")[-1],
                "qualified_name": src,
                "asset_type": "TABLE",
                "certification_status": "UNVERIFIED",
                "owner_name": "External",
            }

        if tgt in asset_map:
            tgt = asset_map[tgt].id
        elif tgt not in nodes_dict:
            nodes_dict[tgt] = {
                "id": tgt,
                "name": tgt.split(".")[-1],
                "qualified_name": tgt,
                "asset_type": "TABLE",
                "certification_status": "UNVERIFIED",
                "owner_name": "External",
            }

        edges.append({
            "id": r.id,
            "source": src,
            "target": tgt,
            "type": r.relationship_type.value,
            "confidence": r.confidence,
        })

    return {"nodes": list(nodes_dict.values()), "edges": edges}

