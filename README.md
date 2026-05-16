# Moulcyber

Moulcyber is a low-latency Moroccan Darija phone assistant for callers who may only have a basic phone line or weak mobile data. The primary production path is Twilio SIP to LiveKit, with a Gemini Live agent handling realtime speech and optional MCP tools.

The project includes:

- `backend/`: FastAPI API for health checks, chat, Twilio webhook fallback, analytics, and ElevenLabs fallback compatibility.
- `livekit_agent/`: LiveKit Agents worker using Gemini Live, Google Search grounding, and configurable MCP toolsets.
- `frontend/`: React/Vite dashboard and demo surface.
- `config/`: LiveKit SIP and MCP configuration examples.
- `deploy/`: Nginx host config for `moulcyber.duckdns.org`.

Secret files are intentionally not tracked. Use `.env.example` as the only committed environment template; keep `.env` and `.env.livekit` local.

## Architecture

Primary inbound call flow:

1. Caller dials `+1 775 406 0061`.
2. Twilio routes the number through Elastic SIP Trunk `moulcyber-livekit`.
3. Twilio sends SIP origination to LiveKit Cloud.
4. LiveKit SIP creates a room and dispatches `moulcyber-live-agent`.
5. The agent speaks through Gemini Live and can call Google Search or MCP tools when needed.

Fallback flows:

- Twilio webhooks can still return LiveKit SIP TwiML if the number is routed to `https://moulcyber.duckdns.org/twilio/inbound`.
- ElevenLabs ConvAI remains available behind `VOICE_PROVIDER=elevenlabs` for rollback.
- `/api/chat` provides a text/chat path using Gemini with Google Search grounding.

## Architecture Diagram

GitHub does not render TikZ directly, but this block can be copied into a LaTeX document that loads `tikz`, `positioning`, and `arrows.meta`.

```tex
\begin{tikzpicture}[
  node distance=1.25cm and 1.65cm,
  box/.style={draw, rounded corners, align=center, minimum width=3.2cm, minimum height=1.0cm},
  store/.style={draw, cylinder, shape border rotate=90, aspect=0.25, align=center, minimum height=1.1cm},
  arrow/.style={-{Latex[length=2mm]}, thick}
]
  \node[box] (caller) {Caller\\PSTN phone};
  \node[box, right=of caller] (twilio) {Twilio\\Elastic SIP Trunk};
  \node[box, right=of twilio] (sip) {LiveKit SIP\\Inbound trunk};
  \node[box, right=of sip] (agent) {LiveKit Agent\\moulcyber-live-agent};
  \node[box, above right=of agent] (gemini) {Gemini Live\\Realtime audio};
  \node[box, below right=of agent] (mcp) {MCP Toolsets\\HTTP or stdio};
  \node[box, below=of sip] (backend) {FastAPI Backend\\health, chat, fallback};
  \node[store, below=of backend] (logs) {JSONL\\analytics logs};
  \node[box, below=of twilio] (eleven) {ElevenLabs\\optional fallback};

  \draw[arrow] (caller) -- node[above]{call} (twilio);
  \draw[arrow] (twilio) -- node[above]{SIP origination} (sip);
  \draw[arrow] (sip) -- node[above]{dispatch room} (agent);
  \draw[arrow] (agent) -- node[above]{audio in/out} (gemini);
  \draw[arrow] (agent) -- node[right]{tools} (mcp);
  \draw[arrow] (backend) -- node[right]{events} (logs);
  \draw[arrow, dashed] (twilio) -- node[left]{webhook fallback} (backend);
  \draw[arrow, dashed] (backend) -- node[below]{VOICE\_PROVIDER=elevenlabs} (eleven);
\end{tikzpicture}
```

## Runtime Path

Confirmed routing:

```text
Twilio number: +17754060061
Twilio trunk: moulcyber-livekit
Twilio trunk domain: moulcyber-livekit.pstn.twilio.com
Twilio origination URL: sip:0c0g2hzfv6c.sip.livekit.cloud;transport=tcp
LiveKit project: moulcyber
LiveKit inbound trunk: ST_N9CgGUScJL8y
LiveKit dispatch rule: SDR_FnGXiBPMwfKo
LiveKit agent name: moulcyber-live-agent
Gemini Live model: gemini-3.1-flash-live-preview
```

## Latency Priorities

The production path avoids an extra STT plus TTS cascade where possible:

- Twilio SIP goes directly to LiveKit SIP.
- LiveKit dispatches one Python agent per call room.
- Gemini Live handles realtime audio input and output.
- `GEMINI_THINKING_LEVEL=minimal` keeps responses short and fast.
- The prompt asks for short spoken answers and avoids unnecessary tool calls.
- MCP is loaded only from configured servers, so empty MCP config adds no external call overhead.

## Local Setup

```bash
cp .env.example .env
lk app env -w -d .env.livekit
docker compose up -d --build
curl -fsS http://127.0.0.1:7331/health
curl -fsS http://127.0.0.1:8081/
```

Expected health shape:

```json
{
  "status": "ok",
  "service": "moulcyber",
  "voice_provider": "livekit",
  "calls_ready": true,
  "livekit_ready": true,
  "chat_ready": true
}
```

Watch the call agent:

```bash
docker compose logs -f livekit-agent
```

## Environment

Required for the LiveKit voice path:

```text
VOICE_PROVIDER=livekit
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_AGENT_NAME=moulcyber-live-agent
LIVEKIT_SIP_URI=sip:0c0g2hzfv6c.sip.livekit.cloud;transport=tcp
GOOGLE_API_KEY=
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_THINKING_LEVEL=minimal
```

Required for backend text/chat:

```text
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

Required only for Twilio REST outbound calls:

```text
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=+17754060061
```

## MCP

MCP servers are configured in `config/mcp.servers.json` and loaded by `livekit_agent/agent.py`.

Empty config:

```json
{
  "servers": []
}
```

HTTP MCP example:

```json
{
  "servers": [
    {
      "id": "search",
      "type": "http",
      "url": "https://example.com/mcp",
      "transport_type": "streamable_http",
      "headers": {
        "Authorization": "Bearer ${SEARCH_MCP_TOKEN}"
      },
      "allowed_tools": ["search"]
    }
  ]
}
```

stdio MCP example:

```json
{
  "servers": [
    {
      "id": "local-tools",
      "type": "stdio",
      "command": "node",
      "args": ["server.js"],
      "cwd": "/app/tools",
      "env": {
        "API_KEY": "${LOCAL_TOOL_API_KEY}"
      },
      "allowed_tools": ["lookup"]
    }
  ]
}
```

When MCP is enabled, the agent combines:

- Gemini provider tools, currently Google Search.
- Explicit MCP toolsets from `config/mcp.servers.json`.
- Voice instructions that restrict tool calls to fresh/current data questions.

## Twilio Checks

Verify the trunk and phone number:

```bash
twilio api:trunking:v1:trunks:list --properties sid,friendlyName,domainName
twilio api:trunking:v1:trunks:origination-urls:list --trunk-sid TKc8fff9e36f81493855785cd5be5faff8
twilio api:core:incoming-phone-numbers:list --phone-number +17754060061 --properties sid,phoneNumber,voiceUrl,trunkSid
```

## LiveKit Checks

```bash
lk project list
lk sip inbound list
lk sip dispatch list
docker compose logs --tail=100 livekit-agent
```

The agent log should include a line similar to:

```text
registered worker ... agent_name=moulcyber-live-agent ... url=wss://moulcyber-7m07suek.livekit.cloud
```

## ElevenLabs Fallback

ElevenLabs is not the primary route. To switch back later:

```text
VOICE_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=
ELEVENLABS_AGENT_ID=
```

Then route Twilio Voice to:

```text
https://moulcyber.duckdns.org/twilio/inbound
```

The backend also keeps `/v1/chat/completions` for Custom LLM compatibility.

## Frontend

```bash
cd frontend
npm install
npm run build
```

Frontend env:

```text
VITE_API_BASE_URL=https://moulcyber.duckdns.org
VITE_SHOW_ELEVENLABS_WIDGET=false
```

Set `VITE_SHOW_ELEVENLABS_WIDGET=true` only when testing the fallback web widget.
