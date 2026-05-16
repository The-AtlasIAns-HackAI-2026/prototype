from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, mcp
from livekit.plugins import google


load_dotenv(".env")
load_dotenv(".env.livekit")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "moulcyber-live-agent")
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "/app/prompts"))
MCP_SERVERS_FILE = Path(os.getenv("MCP_SERVERS_FILE", "/app/config/mcp.servers.json"))


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
3. Sta3mel tools ghir ila kayn soual 3la lyoum, météo, prix, akhbar, aw data khas-ha internet.
4. Ila ma kanch 3andek tool aw data, gol "ma 3endich ta2kid daba" b sra7a.
5. L-hadaf howa latency 9lila: jawb b 1 ta 3 joumal.
""".strip()
    return f"{base}\n\n{live_rules}"


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
