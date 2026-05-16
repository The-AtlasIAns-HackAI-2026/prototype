from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler | None = None


class MCPToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "ready": tool.handler is not None,
            }
            for tool in self._tools.values()
        ]

    async def run(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"MCP tool '{name}' is not registered")
        if tool.handler is None:
            raise RuntimeError(f"MCP tool '{name}' is registered but not implemented")
        return await tool.handler(payload)


registry = MCPToolRegistry()

registry.register(
    MCPTool(
        name="google_search_grounding",
        description="Reserved mapping for Gemini native Google Search grounding.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=None,
    )
)

registry.register(
    MCPTool(
        name="call_metadata_logger",
        description="Reserved mapping for anonymized call metadata logging.",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "language": {"type": "string"},
                "success": {"type": "boolean"},
            },
            "required": ["topic", "language", "success"],
        },
        handler=None,
    )
)
