from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


HOTLINE_API_BASE_URL = os.getenv("HOTLINE_API_BASE_URL", "http://backend:8000").rstrip("/")
HOTLINE_TIMEOUT = float(os.getenv("HOTLINE_API_TIMEOUT", "8"))

mcp = FastMCP(
    "khadamati-hotline",
    instructions=(
        "Khadamati legal and bureaucracy hotline tools. Route first, retrieve cited "
        "legal context, build case packets, and require oral approval before execution."
    ),
)


async def _run_backend_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{HOTLINE_API_BASE_URL}/api/mcp-tools/{tool_name}/run"
    body = {"payload": payload}
    async with httpx.AsyncClient(timeout=HOTLINE_TIMEOUT) as client:
        response = await client.post(url, json=body)
    response.raise_for_status()
    result = response.json()
    return result if isinstance(result, dict) else {"result": result}


def _voice_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "channel": payload.pop("channel", "voice-agent"),
        **{key: value for key, value in payload.items() if value not in (None, "")},
    }


@mcp.tool(description="Route a legal, public-service, or complaint issue to the right Khadamati mini-agent.")
async def hotline_route_issue(
    message: str,
    language: str = "darija",
    city: str = "",
    caller_phone: str = "",
    call_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    provided_fields = {key: value for key, value in {"city": city, "caller_phone": caller_phone}.items() if value}
    return await _run_backend_tool(
        "hotline_route_issue",
        _voice_payload(
            {
                "message": message,
                "language": language,
                "provided_fields": provided_fields,
                "caller_phone": caller_phone,
                "call_id": call_id,
                "trace_id": trace_id,
            }
        ),
    )


@mcp.tool(description="Retrieve cited Moroccan legal context from sector RAG datasets.")
async def legal_rag_retrieve(
    question: str,
    sector: str = "",
    top_k: int = 3,
    merge_related_sectors: bool = True,
    caller_phone: str = "",
    call_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return await _run_backend_tool(
        "legal_rag_retrieve",
        _voice_payload(
            {
                "question": question,
                "sector": sector,
                "top_k": max(1, min(int(top_k or 3), 5)),
                "merge_related_sectors": bool(merge_related_sectors),
                "caller_phone": caller_phone,
                "call_id": call_id,
                "trace_id": trace_id,
            }
        ),
    )


@mcp.tool(description="Build a human-review handoff packet with expert route, nearest article, risks, and missing fields.")
async def case_packet_build(
    topic: str,
    first_name: str = "",
    last_name: str = "",
    caller_phone: str = "",
    city: str = "",
    merge_related_sectors: bool = True,
    call_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return await _run_backend_tool(
        "case_packet_build",
        _voice_payload(
            {
                "topic": topic,
                "first_name": first_name,
                "last_name": last_name,
                "caller_phone": caller_phone,
                "city": city,
                "merge_related_sectors": bool(merge_related_sectors),
                "call_id": call_id,
                "trace_id": trace_id,
            }
        ),
    )


@mcp.tool(description="Start oral approval before a complaint execution action.")
async def approval_flow_start(
    action: str,
    summary: str,
    caller_phone: str = "",
    call_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return await _run_backend_tool(
        "approval_flow_start",
        _voice_payload(
            {
                "action": action,
                "summary": summary,
                "caller_phone": caller_phone,
                "call_id": call_id,
                "trace_id": trace_id,
            }
        ),
    )


@mcp.tool(description="Confirm whether the caller explicitly approved the pending execution action.")
async def approval_flow_confirm(
    approval_id: str,
    spoken_text: str,
    caller_phone: str = "",
    call_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return await _run_backend_tool(
        "approval_flow_confirm",
        _voice_payload(
            {
                "approval_id": approval_id,
                "spoken_text": spoken_text,
                "caller_phone": caller_phone,
                "call_id": call_id,
                "trace_id": trace_id,
            }
        ),
    )


@mcp.tool(description="Submit a mock Chikaya complaint after explicit oral approval.")
async def mock_chikaya_submit(
    first_name: str,
    last_name: str,
    topic: str,
    caller_phone: str,
    consent: bool,
    city: str = "",
    category: str = "",
    desired_resolution: str = "",
    call_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    return await _run_backend_tool(
        "mock_chikaya_submit",
        _voice_payload(
            {
                "first_name": first_name,
                "last_name": last_name,
                "topic": topic,
                "caller_phone": caller_phone,
                "city": city or "not provided",
                "category": category or "legal or administrative complaint",
                "desired_resolution": desired_resolution,
                "consent": bool(consent),
                "source": "voice-agent",
                "call_id": call_id,
                "trace_id": trace_id,
            }
        ),
    )


if __name__ == "__main__":
    mcp.run("stdio")
