from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from hotline_engine import confirm_oral_approval, route_issue, start_oral_approval, submit_mock_chikaya
from legal_rag import retrieve_legal_context


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


async def _route_hotline_issue(payload: dict[str, Any]) -> dict[str, Any]:
    return route_issue(
        message=str(payload.get("message") or ""),
        language=str(payload.get("language") or "darija"),
        provided_fields=payload.get("provided_fields") if isinstance(payload.get("provided_fields"), dict) else {},
    )


async def _submit_mock_chikaya(payload: dict[str, Any]) -> dict[str, Any]:
    return await submit_mock_chikaya(payload)


async def _legal_rag_retrieve(payload: dict[str, Any]) -> dict[str, Any]:
    return retrieve_legal_context(
        question=str(payload.get("question") or payload.get("message") or ""),
        sector=str(payload.get("sector") or "") or None,
        top_k=int(payload.get("top_k") or 4),
    )


async def _approval_flow_start(payload: dict[str, Any]) -> dict[str, Any]:
    return await start_oral_approval(payload)


async def _approval_flow_confirm(payload: dict[str, Any]) -> dict[str, Any]:
    return await confirm_oral_approval(payload)


registry.register(
    MCPTool(
        name="hotline_route_issue",
        description="Routes a Moroccan bureaucracy or legal-risk issue to the best expert desk.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "language": {"type": "string"},
                "provided_fields": {"type": "object"},
            },
            "required": ["message"],
        },
        handler=_route_hotline_issue,
    )
)

registry.register(
    MCPTool(
        name="approval_flow_start",
        description="Starts a consent-gated oral approval flow before execution.",
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["action", "summary"],
        },
        handler=_approval_flow_start,
    )
)

registry.register(
    MCPTool(
        name="approval_flow_confirm",
        description="Confirms oral approval text before execution can proceed.",
        input_schema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string"},
                "spoken_text": {"type": "string"},
            },
            "required": ["approval_id", "spoken_text"],
        },
        handler=_approval_flow_confirm,
    )
)

registry.register(
    MCPTool(
        name="legal_rag_retrieve",
        description="Retrieves cited Moroccan legal context from sector RAG datasets for the legal hotline.",
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "sector": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["question"],
        },
        handler=_legal_rag_retrieve,
    )
)

registry.register(
    MCPTool(
        name="mock_chikaya_submit",
        description="Submits a complaint to the mock Chikaya execution agent after explicit consent.",
        input_schema={
            "type": "object",
            "properties": {
                "citizen_name": {"type": "string"},
                "phone": {"type": "string"},
                "city": {"type": "string"},
                "category": {"type": "string"},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "desired_resolution": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "consent": {"type": "boolean"},
            },
            "required": [
                "citizen_name",
                "phone",
                "city",
                "category",
                "subject",
                "description",
                "desired_resolution",
                "consent",
            ],
        },
        handler=_submit_mock_chikaya,
    )
)
