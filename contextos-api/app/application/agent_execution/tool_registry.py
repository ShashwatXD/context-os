"""Tool Registry and Execution Engine with Explicit Permissions and Idempotency."""

from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ApprovalRequiredError, PermissionDeniedError
from app.domain.entities.asset import Asset, AssetType
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.application.context_retrieval.retrieval_service import ContextRetrievalService


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable,
        requires_approval: bool = False,
        parameters_schema: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.description = description
        self.handler = handler
        self.requires_approval = requires_approval
        self.parameters_schema = parameters_schema or {}


class ToolRegistry:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.retrieval_service = ContextRetrievalService(session)
        self._tools: Dict[str, ToolDefinition] = {}
        self._idempotency_cache: Dict[str, Any] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        self.register(
            ToolDefinition(
                name="search_assets",
                description="Search enterprise metadata catalog by keyword, type, or owner.",
                handler=self._tool_search_assets,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "asset_type": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            )
        )
        self.register(
            ToolDefinition(
                name="get_asset_details",
                description="Retrieve full technical metadata, columns, and ownership of an asset.",
                handler=self._tool_get_asset_details,
                parameters_schema={
                    "type": "object",
                    "properties": {"asset_id": {"type": "string"}},
                    "required": ["asset_id"],
                },
            )
        )
        self.register(
            ToolDefinition(
                name="get_lineage",
                description="Traverse upstream and downstream dependencies for an asset.",
                handler=self._tool_get_lineage,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "depth": {"type": "integer", "default": 3},
                        "direction": {"type": "string", "enum": ["upstream", "downstream", "both"], "default": "both"},
                    },
                    "required": ["asset_id"],
                },
            )
        )
        self.register(
            ToolDefinition(
                name="search_context",
                description="Hybrid retrieval combining vector search, full-text, and lineage traversal.",
                handler=self._tool_search_context,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "asset_types": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["query"],
                },
            )
        )
        self.register(
            ToolDefinition(
                name="get_business_definition",
                description="Fetch certified business definitions and detect conflicting policies.",
                handler=self._tool_get_business_definition,
                parameters_schema={
                    "type": "object",
                    "properties": {"term": {"type": "string"}},
                    "required": ["term"],
                },
            )
        )
        self.register(
            ToolDefinition(
                name="get_asset_owner",
                description="Identify verified technical and business owners for an enterprise asset.",
                handler=self._tool_get_asset_owner,
                parameters_schema={
                    "type": "object",
                    "properties": {"asset_id": {"type": "string"}},
                    "required": ["asset_id"],
                },
            )
        )
        self.register(
            ToolDefinition(
                name="retrieve_source_evidence",
                description="Retrieve raw cryptographic provenance evidence and source record hashes.",
                handler=self._tool_retrieve_source_evidence,
                parameters_schema={
                    "type": "object",
                    "properties": {"provenance_id": {"type": "string"}},
                    "required": ["provenance_id"],
                },
            )
        )
        self.register(
            ToolDefinition(
                name="request_metric_correction",
                description="Sensitive action: Requests formal correction of a conflicting metric.",
                handler=self._tool_request_metric_correction,
                requires_approval=True,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "proposed_definition": {"type": "string"},
                        "reason": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["asset_id", "proposed_definition", "reason", "idempotency_key"],
                },
            )
        )

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "requires_approval": t.requires_approval,
                "parameters_schema": t.parameters_schema,
            }
            for t in self._tools.values()
        ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        caller_permissions: List[str],
        bypass_approval_check: bool = False,
    ) -> Dict[str, Any]:
        """Executes a tool with permission checks, idempotency, and approval barriers."""
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool '{tool_name}'")

        # 1. Permission check
        if "*" not in caller_permissions and tool_name not in caller_permissions:
            raise PermissionDeniedError(actor="Agent", required_permission=f"tool:{tool_name}")

        # 2. Approval check
        if tool.requires_approval and not bypass_approval_check:
            raise ApprovalRequiredError(
                action=tool_name,
                suggestion_id=arguments.get("asset_id", "unknown"),
            )

        # 3. Idempotency Check for side effects
        idempotency_key = arguments.get("idempotency_key")
        if idempotency_key:
            if idempotency_key in self._idempotency_cache:
                return {
                    "result": self._idempotency_cache[idempotency_key],
                    "idempotent_replay": True,
                }

        # 4. Execute tool handler
        output = await tool.handler(arguments)

        # Cache result if idempotent
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = output

        return {"result": output, "idempotent_replay": False}

    # Internal Handlers
    async def _tool_search_assets(self, args: Dict[str, Any]) -> Any:
        return await self.asset_repo.search_assets(
            query=args.get("query"),
            asset_type=args.get("asset_type"),
            limit=args.get("limit", 10),
        )

    async def _tool_get_asset_details(self, args: Dict[str, Any]) -> Any:
        asset = await self.asset_repo.get_by_id(args["asset_id"])
        if not asset:
            return {"error": f"Asset '{args['asset_id']}' not found"}
        return asset.model_dump()

    async def _tool_get_lineage(self, args: Dict[str, Any]) -> Any:
        return await self.relationship_repo.get_lineage(
            asset_id=args["asset_id"],
            depth=args.get("depth", 3),
            direction=args.get("direction", "both"),
        )

    async def _tool_search_context(self, args: Dict[str, Any]) -> Any:
        res = await self.retrieval_service.query_context(
            query=args["query"],
            asset_types=args.get("asset_types"),
        )
        return res.model_dump()

    async def _tool_get_business_definition(self, args: Dict[str, Any]) -> Any:
        term = args["term"]
        assets = await self.asset_repo.search_assets(query=term, limit=5)
        definitions = [
            {
                "asset_id": a.id,
                "name": a.name,
                "definition": a.description,
                "certification_status": a.certification_status.value,
                "owner": a.owner_name,
            }
            for a in assets
        ]
        return {"term": term, "definitions": definitions}

    async def _tool_get_asset_owner(self, args: Dict[str, Any]) -> Any:
        asset = await self.asset_repo.get_by_id(args["asset_id"])
        if not asset:
            return {"error": "Asset not found"}
        return {
            "asset_id": asset.id,
            "name": asset.name,
            "owner_name": asset.owner_name or "Unassigned",
            "certification_status": asset.certification_status.value,
        }

    async def _tool_retrieve_source_evidence(self, args: Dict[str, Any]) -> Any:
        evidence = await self.retrieval_service.retrieve_source_evidence(args["provenance_id"])
        if not evidence:
            return {"error": f"Provenance record '{args['provenance_id']}' not found"}
        return evidence

    async def _tool_request_metric_correction(self, args: Dict[str, Any]) -> Any:
        return {
            "status": "CORRECTION_PROPOSED",
            "asset_id": args["asset_id"],
            "proposed_definition": args["proposed_definition"],
            "reason": args["reason"],
            "idempotency_key": args["idempotency_key"],
        }

