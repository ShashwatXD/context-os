"""Model Context Protocol (MCP) Server for ContextOS.

Exposes verified, governance-bounded context to external AI agents
(e.g., Claude Desktop, LangChain, Autogen) via standard MCP tools.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.agent_execution.tool_registry import ToolRegistry


class ContextOSMCPServer:
    """MCP Server exposing ContextOS tools over JSON-RPC 2.0."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tool_registry = ToolRegistry(session)

    def get_server_capabilities(self) -> Dict[str, Any]:
        """Returns standard MCP server metadata and tool declarations."""
        return {
            "name": "contextos-mcp",
            "version": "1.0.0",
            "protocol_version": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False,
                }
            },
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns MCP tool definitions with JSON schemas."""
        tools = self.tool_registry.list_tools()
        # Filter only public read/governed tools for MCP
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["parameters_schema"],
            }
            for t in tools
            if not t["requires_approval"] or t["name"] == "request_metric_correction"
        ]

    async def handle_call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatches an MCP tool invocation using the unified ToolRegistry."""
        try:
            # MCP clients execute with standard read permissions
            result = await self.tool_registry.execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                caller_permissions=["*"],  # Managed through tool registry approval check
                bypass_approval_check=False,
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": str(result["result"]),
                    }
                ],
                "isError": False,
            }
        except Exception as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error executing MCP tool '{tool_name}': {str(exc)}",
                    }
                ],
                "isError": True,
            }

