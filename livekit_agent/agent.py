from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    JobContext,
    RunContext,
    function_tool,
    mcp,
)
from livekit.plugins import google


load_dotenv(".env")
load_dotenv(".env.livekit")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "moulcyber-live-agent")
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "/app/prompts"))
MCP_SERVERS_FILE = Path(os.getenv("MCP_SERVERS_FILE", "/app/config/mcp.servers.json"))
HOTLINE_API_BASE_URL = os.getenv("HOTLINE_API_BASE_URL", "http://backend:8000").rstrip("/")
HOTLINE_TIMEOUT = float(os.getenv("HOTLINE_API_TIMEOUT", "8"))


def _clean_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if value in {"", '""', "''"}:
        return None
    return value


google_api_key = _clean_env_value("GOOGLE_API_KEY") or _clean_env_value("GEMINI_API_KEY")
if google_api_key:
    os.environ["GOOGLE_API_KEY"] = google_api_key
    os.environ.pop("GEMINI_API_KEY", None)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _expand_env(value: str) -> str:
    pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
    return pattern.sub(lambda match: os.getenv(match.group(1), ""), value)


def _expand_env_in_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    expanded: dict[str, str] = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            expanded[key] = _expand_env(value)
        else:
            expanded[key] = str(value)
    return expanded


def _read_prompt() -> str:
    prompt_file = PROMPTS_DIR / "khadamati_darija.txt"
    if prompt_file.exists():
        base = prompt_file.read_text(encoding="utf-8").strip()
    else:
        base = (
            'Nta smitek "Khadamati". Jawb b-Darija Maghribiya, '
            "b joumal 9sar, bla markdown, bla URLs."
        )

    live_rules = """

LIVE CALL RULES:
1. Smitk "Khadamati". Hadi mokalama telephone. Jawb b sawt, b joumal 9sar, w khalli l-user ykammel ila qta3ek.
2. Ila l-user sket, matbda ta mawdo3 jdid. Tsennah ytkellem.
3. Workflow strict: ay soual qanouni aw idari khaso route_hotline_issue awalan. Ila kayn qanoun, khas query_legal_knowledge_base taniyan. Matjawbch mn memory.
4. Jawb ghir men retrieved context. Bda b article/fasl/madda ila kayn. Ila l-source fih articles bzzaf, gol kaynin bzzaf w smmi l-aqrab l-soual.
5. Ila ma l9itich article/source, gol "ma 3endich source kafi daba" w sowwel soual wa7ed, bla general info.
6. Qbel ay submit: start_oral_approval_flow, qra chno ghadi ytsift, tsennah "mwafeq", confirm_oral_approval_flow, عاد submit. F had prototype submission mock-only.
7. F Chikaya, matsewelch 3la telephone. Telephone kaytakhod automatique men l-caller. Sewwel ghir first name, last name, w topic/probleme. Ila caller phone ma banche, gol system ma 3rafch number w submission maymknch.
8. Ila l-user bgha tbdl l-mawdo3 l action aw human review, build_case_handoff_packet باش tkhrej packet فيه article, missing fields, evidence, risk.
9. Sta3mel l-internet ghir ila khas ta2kid rasmi/jdid barra dataset.
10. L-hadaf latency 9lila: retrieval tool low-latency, jawb b 1 ta 3 joumal.
""".strip()
    return f"{base}\n\n{live_rules}"


async def _post_hotline(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{HOTLINE_API_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=HOTLINE_TIMEOUT) as client:
        response = await client.post(url, json=payload)
    response.raise_for_status()
    return response.json()


async def _emit_call_event(payload: dict[str, Any]) -> None:
    try:
        await _post_hotline("/api/call-events", payload)
    except Exception:
        return


def _json_mapping(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_call_context(ctx: JobContext, participant: Any | None = None) -> dict[str, Any]:
    room = ctx.room
    attrs = getattr(participant, "attributes", None) or {}
    metadata = _json_mapping(getattr(participant, "metadata", None))
    room_metadata = _json_mapping(getattr(room, "metadata", None))
    merged = {**room_metadata, **metadata, **attrs}

    caller_phone = (
        merged.get("sip.phoneNumber")
        or merged.get("sip.phone_number")
        or merged.get("sip.from")
        or merged.get("from")
        or merged.get("caller_phone")
        or merged.get("phone")
    )
    call_id = (
        merged.get("sip.callID")
        or merged.get("sip.callId")
        or merged.get("sip.call_id")
        or merged.get("twilio.callSid")
        or merged.get("call_sid")
        or merged.get("call_id")
        or getattr(participant, "sid", None)
        or getattr(room, "sid", None)
    )
    return {
        "channel": "voice-agent",
        "call_id": str(call_id or ""),
        "caller_phone": str(caller_phone or ""),
        "call_status": str(merged.get("sip.callStatus") or merged.get("call_status") or ""),
        "room_name": str(getattr(room, "name", "") or ""),
        "participant_identity": str(getattr(participant, "identity", "") or ""),
    }


def _load_mcp_toolsets() -> list[Any]:
    if not _env_bool("MCP_ENABLED", True):
        return []
    if not MCP_SERVERS_FILE.exists():
        return []

    config = json.loads(MCP_SERVERS_FILE.read_text(encoding="utf-8"))
    toolsets: list[Any] = []

    for server in config.get("servers", []):
        server_id = server.get("id") or server.get("name")
        server_type = (server.get("type") or "http").lower()
        if not server_id:
            continue

        allowed_tools = server.get("allowed_tools") or None

        if server_type == "http":
            url = server.get("url")
            if not url:
                continue
            headers = _expand_env_in_mapping(server.get("headers", {}))
            toolsets.append(
                mcp.MCPToolset(
                    id=server_id,
                    mcp_server=mcp.MCPServerHTTP(
                        _expand_env(url),
                        transport_type=server.get("transport_type"),
                        headers=headers or None,
                        allowed_tools=allowed_tools,
                    ),
                )
            )
        elif server_type == "stdio":
            command = server.get("command")
            if not command:
                continue
            toolsets.append(
                mcp.MCPToolset(
                    id=server_id,
                    mcp_server=mcp.MCPServerStdio(
                        command=command,
                        args=[_expand_env(str(arg)) for arg in server.get("args", [])],
                        cwd=server.get("cwd"),
                        env=_expand_env_in_mapping(server.get("env", {})) or None,
                    ),
                )
            )

    return toolsets


def _build_tools() -> list[Any]:
    tools = []
    if _env_bool("GEMINI_ENABLE_GOOGLE_SEARCH", True):
        tools.append(google.tools.GoogleSearch())
    tools.extend(_load_mcp_toolsets())
    return tools


class KhadamatiAgent(Agent):
    def __init__(self, call_context: dict[str, Any] | None = None) -> None:
        self.call_context = call_context or {"channel": "voice-agent"}
        super().__init__(
            instructions=_read_prompt(),
            tools=_build_tools(),
        )

    def _payload(self, payload: dict[str, Any], tool: str) -> dict[str, Any]:
        return {
            **payload,
            "channel": self.call_context.get("channel") or "voice-agent",
            "call_id": self.call_context.get("call_id") or "",
            "caller_phone": self.call_context.get("caller_phone") or "",
            "trace_id": self.call_context.get("call_id") or "",
            "tool": tool,
        }

    async def _log_tool_result(
        self,
        *,
        tool: str,
        success: bool,
        result: dict[str, Any] | None = None,
        latency_ms: float | None = None,
    ) -> None:
        route = None
        article = None
        if result:
            route_payload = result.get("route")
            if isinstance(route_payload, dict):
                route = route_payload.get("sector")
            if isinstance(result.get("results"), list) and result["results"]:
                article = result["results"][0].get("primary_article")
        await _emit_call_event(
            {
                **self.call_context,
                "event_type": "tool_result",
                "tool": tool,
                "route": route,
                "article": article,
                "latency_ms": latency_ms,
                "success": success,
            }
        )

    @function_tool()
    async def route_hotline_issue(
        self,
        context: RunContext,
        issue: str,
        language: str = "darija",
        city: str = "",
    ) -> str:
        """Route a bureaucracy, public service, complaint, or legal-risk issue to the right expert desk.

        Args:
            issue: The caller's issue in their own words.
            language: Caller language, usually darija or fr.
            city: City or location if the caller gave one.
        """
        try:
            started = asyncio.get_running_loop().time()
            result = await _post_hotline(
                "/api/hotline/triage",
                self._payload(
                    {
                        "message": issue,
                        "language": language,
                        "city": city or None,
                    },
                    "hotline_route_issue",
                ),
            )
        except Exception as exc:
            await self._log_tool_result(tool="hotline_route_issue", success=False)
            return json.dumps(
                {
                    "error": "hotline_engine_unavailable",
                    "detail": str(exc),
                    "fallback": "Ask one short clarifying question and avoid legal conclusions.",
                },
                ensure_ascii=False,
            )
        await self._log_tool_result(
            tool="hotline_route_issue",
            success=True,
            result=result,
            latency_ms=round((asyncio.get_running_loop().time() - started) * 1000, 2),
        )
        return json.dumps(result, ensure_ascii=False)

    @function_tool()
    async def query_legal_knowledge_base(
        self,
        context: RunContext,
        question: str,
        sector: str = "",
        top_k: int = 3,
    ) -> str:
        """Retrieve cited Moroccan legal context from the local RAG sector mini-agents.

        Args:
            question: The caller's legal question.
            sector: Optional sector slug such as family_law, criminal_law, civil_procedure, constitutional_law, or public_finance.
            top_k: Number of source chunks to retrieve. Use 3 for lowest latency.
        """
        try:
            started = asyncio.get_running_loop().time()
            result = await _post_hotline(
                "/api/legal-rag/query",
                self._payload(
                    {
                        "question": question,
                        "sector": sector or None,
                        "top_k": max(1, min(int(top_k or 3), 5)),
                        "use_llm": False,
                    },
                    "legal_rag_retrieve",
                ),
            )
        except Exception as exc:
            await self._log_tool_result(tool="legal_rag_retrieve", success=False)
            return json.dumps(
                {
                    "error": "legal_rag_unavailable",
                    "detail": str(exc),
                    "fallback": "Say retrieval is unavailable and ask one clarifying question.",
                },
                ensure_ascii=False,
            )
        await self._log_tool_result(
            tool="legal_rag_retrieve",
            success=True,
            result=result,
            latency_ms=round((asyncio.get_running_loop().time() - started) * 1000, 2),
        )
        return json.dumps(result, ensure_ascii=False)

    @function_tool()
    async def start_oral_approval_flow(
        self,
        context: RunContext,
        action: str,
        summary: str,
    ) -> str:
        """Start an oral approval flow before a mock execution action.

        Args:
            action: The execution action being prepared.
            summary: A concise summary of what will be submitted or executed.
        """
        try:
            result = await _post_hotline(
                "/api/hotline/approval/start",
                self._payload(
                    {
                        "action": action,
                        "summary": summary,
                    },
                    "approval_flow_start",
                ),
            )
        except Exception as exc:
            await self._log_tool_result(tool="approval_flow_start", success=False)
            return json.dumps(
                {
                    "error": "approval_flow_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        await self._log_tool_result(tool="approval_flow_start", success=True, result=result)
        return json.dumps(result, ensure_ascii=False)

    @function_tool()
    async def build_case_handoff_packet(
        self,
        context: RunContext,
        topic: str,
        first_name: str = "",
        last_name: str = "",
        city: str = "",
    ) -> str:
        """Build a structured handoff packet for legal aid, human review, or complaint execution.

        Args:
            topic: The caller's legal or administrative issue.
            first_name: Caller first name if already collected.
            last_name: Caller last name if already collected.
            city: City if already known.
        """
        try:
            result = await _post_hotline(
                "/api/hotline/case-packet",
                self._payload(
                    {
                        "topic": topic,
                        "first_name": first_name or None,
                        "last_name": last_name or None,
                        "city": city or None,
                    },
                    "case_packet_build",
                ),
            )
        except Exception as exc:
            await self._log_tool_result(tool="case_packet_build", success=False)
            return json.dumps(
                {
                    "error": "case_packet_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        await self._log_tool_result(tool="case_packet_build", success=True, result=result)
        return json.dumps(result, ensure_ascii=False)

    @function_tool()
    async def confirm_oral_approval_flow(
        self,
        context: RunContext,
        approval_id: str,
        spoken_text: str,
    ) -> str:
        """Confirm whether the caller gave explicit oral approval.

        Args:
            approval_id: Approval id returned by start_oral_approval_flow.
            spoken_text: The caller's exact spoken approval or rejection.
        """
        try:
            result = await _post_hotline(
                "/api/hotline/approval/confirm",
                self._payload(
                    {
                        "approval_id": approval_id,
                        "spoken_text": spoken_text,
                    },
                    "approval_flow_confirm",
                ),
            )
        except Exception as exc:
            await self._log_tool_result(tool="approval_flow_confirm", success=False)
            return json.dumps(
                {
                    "approved": False,
                    "error": "approval_confirmation_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        await self._log_tool_result(tool="approval_flow_confirm", success=bool(result.get("approved")), result=result)
        return json.dumps(result, ensure_ascii=False)

    @function_tool()
    async def submit_mock_chikaya_complaint(
        self,
        context: RunContext,
        first_name: str,
        last_name: str,
        topic: str,
        city: str = "",
        category: str = "",
        desired_resolution: str = "",
        consent: bool = False,
    ) -> str:
        """Submit a complaint to the mock Chikaya website only after explicit consent.

        Args:
            first_name: Citizen first name.
            last_name: Citizen last name.
            topic: The caller's complaint topic/problem in their own words.
            city: City related to the complaint if already known.
            category: Complaint category if already known.
            desired_resolution: What the citizen wants fixed if already known.
            consent: True only if the caller explicitly agreed to submit the mock complaint.
        """
        caller_phone = self.call_context.get("caller_phone") or ""
        try:
            result = await _post_hotline(
                "/api/hotline/chikaya/mock-submit",
                self._payload(
                    {
                        "first_name": first_name,
                        "last_name": last_name,
                        "topic": topic,
                        "caller_phone": caller_phone,
                        "city": city or "not provided",
                        "category": category or "legal or administrative complaint",
                        "desired_resolution": desired_resolution
                        or "Request a clear written answer and guidance about the next administrative step.",
                        "evidence": [],
                        "consent": consent,
                        "source": "voice-agent",
                    },
                    "mock_chikaya_submit",
                ),
            )
        except Exception as exc:
            await self._log_tool_result(tool="mock_chikaya_submit", success=False)
            return json.dumps(
                {
                    "submitted": False,
                    "error": "mock_chikaya_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        await self._log_tool_result(tool="mock_chikaya_submit", success=bool(result.get("submitted")), result=result)
        return json.dumps(result, ensure_ascii=False)


server = AgentServer(
    host="0.0.0.0",
    port=int(os.getenv("LIVEKIT_AGENT_PORT", "8081")),
)


@server.rtc_session(agent_name=AGENT_NAME)
async def khadamati_live_agent(ctx: JobContext):
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if google_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = google_key

    call_context = _extract_call_context(ctx, None)

    model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            model=model,
            voice=os.getenv("GEMINI_LIVE_VOICE", "Puck"),
            temperature=_env_float("GEMINI_LIVE_TEMPERATURE", 0.35),
            instructions=_read_prompt(),
            thinking_config={
                "thinking_level": os.getenv("GEMINI_THINKING_LEVEL", "minimal"),
            },
        ),
    )

    await session.start(
        room=ctx.room,
        agent=KhadamatiAgent(call_context),
    )

    background_audio = BackgroundAudioPlayer(
        thinking_sound=AudioConfig(BuiltinAudioClip.HOLD_MUSIC, volume=0.16)
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    ctx.add_shutdown_callback(background_audio.aclose)

    try:
        participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=8)
        call_context.update(_extract_call_context(ctx, participant))
    except Exception:
        participant = None
    await _emit_call_event({**call_context, "event_type": "session_started", "success": True})


if __name__ == "__main__":
    agents.cli.run_app(server)
