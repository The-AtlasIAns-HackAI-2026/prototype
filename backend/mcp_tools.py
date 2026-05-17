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
LEGAL_RAG_SECTORS = {
    "family_law",
    "criminal_law",
    "civil_procedure",
    "constitutional_law",
    "public_finance",
}

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


async def _case_packet_build(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload.get("topic") or payload.get("question") or payload.get("message") or "")
    triage = route_issue(
        message=topic,
        language=str(payload.get("language") or "darija"),
        provided_fields={
            key: payload.get(key)
            for key in ("first_name", "last_name", "caller_phone", "city", "topic")
            if payload.get(key)
        },
    )
    selected_expert_id = (triage.get("selected_expert") or {}).get("id")
    retrieval = retrieve_legal_context(
        question=topic,
        sector=selected_expert_id if selected_expert_id in LEGAL_RAG_SECTORS else None,
        top_k=int(payload.get("top_k") or 3),
    )
    first_source = (retrieval.get("results") or [{}])[0]
    return {
        "topic": topic,
        "master_agent": "khadamati_legal_master",
        "selected_expert": triage.get("selected_expert"),
        "missing_fields": triage.get("missing_fields", []),
        "risk_flags": triage.get("risk_flags", []),
        "evidence_checklist": triage.get("evidence_checklist", []),
        "recommended_action": triage.get("recommended_action"),
        "rag_route": retrieval.get("route"),
        "primary_article": first_source.get("primary_article"),
        "article_count": first_source.get("article_count"),
        "chunk_id": first_source.get("chunk_id"),
        "pages": [first_source.get("page_start"), first_source.get("page_end")],
        "a2a_trace": retrieval.get("a2a_trace"),
    }


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
        name="case_packet_build",
        description="Builds a human-review handoff packet with routing, nearest article, missing facts, evidence, and risk flags.",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "caller_phone": {"type": "string"},
                "city": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["topic"],
        },
        handler=_case_packet_build,
    )
)

registry.register(
    MCPTool(
        name="mock_chikaya_submit",
        description="Submits a complaint to the mock Chikaya execution agent after explicit consent.",
        input_schema={
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "topic": {"type": "string"},
                "caller_phone": {"type": "string"},
                "city": {"type": "string"},
                "category": {"type": "string"},
                "citizen_name": {"type": "string"},
                "phone": {"type": "string"},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "desired_resolution": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "consent": {"type": "boolean"},
            },
            "required": [
                "first_name",
                "last_name",
                "topic",
                "consent",
            ],
        },
        handler=_submit_mock_chikaya,
    )
)
