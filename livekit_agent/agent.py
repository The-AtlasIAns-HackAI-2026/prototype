from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RunContext, function_tool, mcp
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
    prompt_file = PROMPTS_DIR / "moulcyber_darija.txt"
    if prompt_file.exists():
        base = prompt_file.read_text(encoding="utf-8").strip()
    else:
        base = (
            'Nta smitek "Moulcyber". Jawb b-Darija Maghribiya, '
            "b joumal 9sar, bla markdown, bla URLs."
        )

    live_rules = """

LIVE CALL RULES:
1. Hadi mokalama telefoon. Jawb b sawt, b joumal 9sar, w khalli l-user ykammel ila qta3ek.
2. Ila l-user sket, mat3awdch t7ell mawdo3 jdid. Tsennah ytkellem.
3. Hadi legal hotline. Ila kayn soual qanouni, route b route_hotline_issue, men b3d jib nass qanouni b query_legal_knowledge_base.
4. Jawb men retrieved context ghir. Dker source b tariqa 9sira: chunk/page.
5. Mat3tich fatwa qanouniya niha2iya. Gol "hadi ma3louma 3amma, machi istichara niha2iya" f l7alat l-qanouniya.
6. Qbel ay submit: start_oral_approval_flow, qra l-user chno ghadi ytsift, tsennah ygol "mwafeq", confirm_oral_approval_flow, عاد submit. F had prototype submission mock-only.
7. Sta3mel l-outil d'internet ghir ila khas ta2kid rasmi/jdid barra dataset.
8. Ila ma kanch 3andek tool aw data, gol "ma 3endich ta2kid daba" b sra7a.
9. L-hadaf howa latency 9lila: retrieval tool low-latency, jawb b 1 ta 3 joumal.
""".strip()
    return f"{base}\n\n{live_rules}"


async def _post_hotline(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{HOTLINE_API_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=HOTLINE_TIMEOUT) as client:
        response = await client.post(url, json=payload)
    response.raise_for_status()
    return response.json()


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
                        allowed_tools=allowed_tools,
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


class MoulcyberAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=_read_prompt(),
            tools=_build_tools(),
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
            result = await _post_hotline(
                "/api/hotline/triage",
                {
                    "message": issue,
                    "language": language,
                    "city": city or None,
                },
            )
        except Exception as exc:
            return json.dumps(
                {
                    "error": "hotline_engine_unavailable",
                    "detail": str(exc),
                    "fallback": "Ask one short clarifying question and avoid legal conclusions.",
                },
                ensure_ascii=False,
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
            result = await _post_hotline(
                "/api/legal-rag/query",
                {
                    "question": question,
                    "sector": sector or None,
                    "top_k": max(1, min(int(top_k or 3), 5)),
                    "use_llm": False,
                },
            )
        except Exception as exc:
            return json.dumps(
                {
                    "error": "legal_rag_unavailable",
                    "detail": str(exc),
                    "fallback": "Say retrieval is unavailable and ask one clarifying question.",
                },
                ensure_ascii=False,
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
                {
                    "action": action,
                    "summary": summary,
                },
            )
        except Exception as exc:
            return json.dumps(
                {
                    "error": "approval_flow_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
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
                {
                    "approval_id": approval_id,
                    "spoken_text": spoken_text,
                },
            )
        except Exception as exc:
            return json.dumps(
                {
                    "approved": False,
                    "error": "approval_confirmation_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        return json.dumps(result, ensure_ascii=False)

    @function_tool()
    async def submit_mock_chikaya_complaint(
        self,
        context: RunContext,
        citizen_name: str,
        phone: str,
        city: str,
        category: str,
        subject: str,
        description: str,
        desired_resolution: str,
        consent: bool,
    ) -> str:
        """Submit a complaint to the mock Chikaya website only after explicit consent.

        Args:
            citizen_name: Citizen full name for the mock complaint.
            phone: Citizen phone number.
            city: City related to the complaint.
            category: Complaint category.
            subject: Short complaint subject.
            description: Detailed complaint story.
            desired_resolution: What the citizen wants fixed.
            consent: True only if the caller explicitly agreed to submit the mock complaint.
        """
        try:
            result = await _post_hotline(
                "/api/hotline/chikaya/mock-submit",
                {
                    "citizen_name": citizen_name,
                    "phone": phone,
                    "city": city,
                    "category": category,
                    "subject": subject,
                    "description": description,
                    "desired_resolution": desired_resolution,
                    "evidence": [],
                    "consent": consent,
                    "source": "voice-agent",
                },
            )
        except Exception as exc:
            return json.dumps(
                {
                    "submitted": False,
                    "error": "mock_chikaya_unavailable",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
        return json.dumps(result, ensure_ascii=False)


server = AgentServer(
    host="0.0.0.0",
    port=int(os.getenv("LIVEKIT_AGENT_PORT", "8081")),
)


@server.rtc_session(agent_name=AGENT_NAME)
async def moulcyber_live_agent(ctx: JobContext):
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if google_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = google_key

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
        agent=MoulcyberAgent(),
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
