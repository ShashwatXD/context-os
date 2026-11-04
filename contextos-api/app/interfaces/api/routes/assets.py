"""Catalog Assets & Lineage API Routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.interfaces.api.dependencies import get_asset_repo, get_relationship_repo
from app.interfaces.api.schemas.api_schemas import (
    AssetDetail,
    AssetSummary,
    ColumnSchema,
    LineageGraphResponse,
)

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("", response_model=List[AssetSummary])
async def list_assets(
    query: Optional[str] = None,
    asset_type: Optional[str] = None,
    certification: Optional[str] = None,
    owner: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    asset_repo: AssetRepository = Depends(get_asset_repo),
):
    assets = await asset_repo.search_assets(
        query=query,
        asset_type=asset_type,
        certification_status=certification,
        owner_name=owner,
        limit=limit,
        offset=offset,
    )
    return [
        AssetSummary(
            id=a.id,
            source_id=a.source_id,
            external_id=a.external_id,
            name=a.name,
            qualified_name=a.qualified_name,
            asset_type=a.asset_type.value,
            description=a.description,
            certification_status=a.certification_status.value,
            owner_name=a.owner_name,
            created_at=a.created_at,
        )
        for a in assets
    ]


@router.get("/{asset_id}", response_model=AssetDetail)
async def get_asset_by_id(
    asset_id: str,
    asset_repo: AssetRepository = Depends(get_asset_repo),
):
    asset = await asset_repo.get_by_id(asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with ID '{asset_id}' not found",
        )
    cols = [
        ColumnSchema(
            name=c.name,
            data_type=c.data_type,
            is_primary_key=c.is_primary_key,
            is_nullable=c.is_nullable,
            description=c.description,
        )
        for c in asset.columns
    ]
    return AssetDetail(
        id=asset.id,
        source_id=asset.source_id,
        external_id=asset.external_id,
        name=asset.name,
        qualified_name=asset.qualified_name,
        asset_type=asset.asset_type.value,
        description=asset.description,
        certification_status=asset.certification_status.value,
        owner_name=asset.owner_name,
        columns=cols,
        tags=asset.tags,
        metadata_payload=asset.metadata_payload,
        provenance_id=asset.provenance_id,
        created_at=asset.created_at,
    )


@router.get("/{asset_id}/lineage", response_model=LineageGraphResponse)
async def get_asset_lineage(
    asset_id: str,
    depth: int = 3,
    direction: str = "both",
    relationship_repo: RelationshipRepository = Depends(get_relationship_repo),
):
    graph = await relationship_repo.get_lineage(asset_id=asset_id, depth=depth, direction=direction)
    return LineageGraphResponse(
        root_asset_id=graph["root_asset_id"],
        depth=graph["depth"],
        direction=graph["direction"],
        nodes=graph["nodes"],
        edges=graph["edges"],
    )

