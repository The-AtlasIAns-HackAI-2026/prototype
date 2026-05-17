# Moulcyber Legal Hotline

Moulcyber is a low-latency Moroccan legal hotline for callers who may only have a basic phone line or weak mobile data. The primary production path is Twilio SIP to LiveKit, with a Gemini Live voice agent orchestrating a legal master agent, sector mini-agents, local RAG datasets, MCP-style tools, oral approval, and mock complaint execution.

The main product is now the legal hotline. Bureaucracy and complaint filing still exist, but as legal-adjacent execution flows behind explicit consent rather than as the core experience.

The project includes:

- `backend/`: FastAPI API for health checks, chat, Twilio fallback TwiML, legal RAG, hotline routing, oral approval, MCP-style tools, and mock Chikaya execution.
- `livekit_agent/`: LiveKit Agents worker using Gemini Live, low-latency function tools, optional Google Search, and configurable MCP toolsets.
- `frontend/`: React/Vite dashboard with the `Hotline` tab as the main demo surface.
- `config/`: LiveKit SIP, legal hotline A2A orchestration, and MCP configuration examples.
- `rag_datasets/`: sector-separated Moroccan legal RAG datasets generated from the uploaded PDFs.
- `datasets/`: placeholder JSONL datasets for execution and complaint workflows, ready to be replaced with vetted content.
- `deploy/`: Nginx host config for `moulcyber.duckdns.org`.

Secret files are intentionally not tracked. Use `.env.example` as the only committed environment template; keep `.env` and `.env.livekit` local.

## Architecture

Primary inbound call flow:

1. Caller dials `+1 775 406 0061`.
2. Twilio routes the number through Elastic SIP Trunk `moulcyber-livekit`.
3. Twilio sends SIP origination to LiveKit Cloud.
4. LiveKit SIP creates a room and dispatches `moulcyber-live-agent`.
5. Gemini Live handles realtime audio input and output in the same session.
6. The agent routes legal questions through a master-slave A2A legal orchestrator.
7. Sector mini-agents retrieve cited context from local Moroccan legal RAG datasets.
8. MCP-style tools handle approval, audit, and mock Chikaya execution when needed.

Fallback flows:

- Twilio webhooks can still return LiveKit SIP TwiML if the number is routed to `https://moulcyber.duckdns.org/twilio/inbound`.
- ElevenLabs ConvAI remains available behind `VOICE_PROVIDER=elevenlabs` for rollback.
- `/api/chat` provides a text/chat path using Gemini with Google Search grounding.
- `/api/legal-rag/*` provides local legal retrieval and optional backend Gemini answers.
- `/api/hotline/*` provides legal-adjacent routing, oral approval, and mock Chikaya execution.

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
  \node[box, right=of agent] (router) {Legal Master\\A2A router};
  \node[box, above right=of router] (experts) {Sector Mini-Agents\\family, criminal, civil};
  \node[store, right=of experts] (rag) {Legal RAG\\chunks + embeddings};
  \node[box, below right=of router] (executor) {Execution Agent\\mock Chikaya};
  \node[box, below=of agent] (mcp) {MCP Toolsets\\approval + execution};
  \node[box, below=of sip] (backend) {FastAPI Backend\\RAG, MCP, hotline};
  \node[store, below=of backend] (logs) {JSONL\\analytics logs};
  \node[box, below=of twilio] (eleven) {ElevenLabs\\optional fallback};

  \draw[arrow] (caller) -- node[above]{call} (twilio);
  \draw[arrow] (twilio) -- node[above]{SIP origination} (sip);
  \draw[arrow] (sip) -- node[above]{dispatch room} (agent);
  \draw[arrow] (agent) -- node[above]{audio in/out} (gemini);
  \draw[arrow] (agent) -- node[above]{function tools} (router);
  \draw[arrow] (router) -- node[above]{A2A route} (experts);
  \draw[arrow] (experts) -- node[above]{retrieve} (rag);
  \draw[arrow] (router) -- node[right]{consent gate} (executor);
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
Legal RAG sectors: family_law, constitutional_law, civil_procedure, criminal_law, public_finance
```

## Hotline Orchestration

The hotline engine is data-driven. `config/hotline/experts.json` defines the master-slave A2A legal topology:

- `legal_safety`: court, police, safety, deadlines, minors, eviction, and human escalation.
- `family_law`: marriage, divorce, custody, filiation, maintenance, and family court context.
- `criminal_law`: crimes, penalties, police/legal-safety triage, and criminal-code context.
- `civil_procedure`: lawsuits, judgments, appeals, enforcement, jurisdiction, and procedure.
- `constitutional_law`: rights, freedoms, institutions, government, and constitutional context.
- `public_finance`: tax, customs, budget, and 2026 finance-law context.
- `chikaya_complaints`: complaint packet builder and consent-gated mock execution.

Each mini-agent has a model hint and dataset path. The current implementation routes to the right sector and retrieves cited context locally; later, each mini-agent can be backed by its own specialized model and vetted dataset without changing the LiveKit call path.

The engine returns the selected expert, candidate experts, missing intake fields, next questions, evidence checklist, safety flags, dataset readiness, and recommended next action. Legal RAG responses also include an explicit A2A trace from `moulcyber_legal_master` to the selected sector mini-agent.

## Legal RAG Dataset

The uploaded PDFs were converted into `rag_datasets/`:

- `family-law-morocco.pdf`: 65 family-law chunks.
- `constitution.pdf`: 57 constitutional-law chunks.
- `civil.pdf`: 149 civil-procedure chunks.
- `criminal-laws.pdf`: 430 criminal-law chunks.
- `finance-project-2026.pdf`: 116 public-finance chunks.

Each sector includes `pages.jsonl`, `chunks.jsonl`, `embeddings.npy`, and metadata. The phone path uses fast local retrieval with `use_llm=false` so Gemini Live can speak from retrieved context without making a second backend model call. The embeddings are kept for a later dense retrieval upgrade.

Example legal RAG checks:

```bash
curl -fsS http://127.0.0.1:7331/api/legal-rag/status

curl -fsS -X POST http://127.0.0.1:7331/api/legal-rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chno kaygol qanoun lmaghribi 3la l7adana ba3d talaq?","language":"darija","top_k":3,"use_llm":false}'

curl -fsS -X POST http://127.0.0.1:7331/api/legal-rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chno l3o9oba dyal sari9a f lqanoun jinai?","language":"darija","top_k":3,"use_llm":false}'
```

## Mock Chikaya Execution

The execution agent is currently mock-only. It simulates opening and filing a complaint through a local mini Chikaya flow in the frontend, then writes an audit receipt to `logs/mock_chikaya_submissions.jsonl`.

Execution is blocked unless required fields are present, `consent=true`, and the target is the mock endpoint. On the voice path, consent is oral: the agent starts an approval flow, reads the action summary back to the caller, waits for the caller to say `mwafeq`, confirms the phrase, then submits. The real Chikaya automation should be added later as a separate driver behind the same execution interface, with a production safety gate and human review.

Jury demo path:

1. Open the `Hotline` tab in the frontend.
2. Ask a legal RAG example and show the selected sector, sources, and A2A trace.
3. Route a complaint request and review missing fields/evidence.
4. Start oral approval, confirm `mwafeq`, then submit the mock Chikaya form.
5. Show the receipt and audit list.

## Latency Priorities

The production path avoids an extra STT plus TTS cascade where possible:

- Twilio SIP goes directly to LiveKit SIP.
- LiveKit dispatches one Python agent per call room.
- Gemini Live handles realtime audio input and output.
- `GEMINI_THINKING_LEVEL=minimal` keeps responses short and fast.
- The prompt asks for short spoken answers and avoids unnecessary tool calls.
- MCP is loaded only from configured servers, so empty MCP config adds no external call overhead.
- Legal RAG retrieval is local and can run without an extra backend LLM call.
- The optional backend Gemini answer path is separate and can be slower; the phone path keeps Gemini Live in the realtime session and passes retrieved context through tools.

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
  "hotline_ready": true,
  "legal_rag_ready": true,
  "chat_ready": true
}
```

Watch the call agent:

```bash
docker compose logs -f livekit-agent
```

Test hotline APIs:

```bash
curl -fsS http://127.0.0.1:7331/api/legal-rag/status

curl -fsS -X POST http://127.0.0.1:7331/api/legal-rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chno l3o9oba dyal sari9a f lqanoun jinai?","language":"darija","top_k":3,"use_llm":false}'

curl -fsS -X POST http://127.0.0.1:7331/api/hotline/triage \
  -H 'Content-Type: application/json' \
  -d '{"message":"Jani istid3a mn lmahkama w ma 3raftch deadline dyal listi2naf","language":"darija"}'

curl -fsS http://127.0.0.1:7331/api/hotline/experts
curl -fsS http://127.0.0.1:7331/api/mcp-tools
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
HOTLINE_API_BASE_URL=http://backend:8000
HOTLINE_API_TIMEOUT=8
HOTLINE_EXPERTS_FILE=/app/config/hotline/experts.json
MOCK_CHIKAYA_LOG_FILE=/app/logs/mock_chikaya_submissions.jsonl
ORAL_APPROVAL_LOG_FILE=/app/logs/oral_approvals.jsonl
LEGAL_RAG_DIR=/app/rag_datasets
GOOGLE_API_KEY=
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_THINKING_LEVEL=minimal
MCP_ENABLED=true
MCP_SERVERS_FILE=/app/config/mcp.servers.json
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
- Backend MCP-style tools for legal RAG, hotline routing, oral approval, and mock Chikaya execution.
- Voice instructions that restrict tool calls to fresh/current data questions.

Backend tool registry:

```text
GET  /api/mcp-tools
POST /api/mcp-tools/hotline_route_issue/run
POST /api/mcp-tools/legal_rag_retrieve/run
POST /api/mcp-tools/approval_flow_start/run
POST /api/mcp-tools/approval_flow_confirm/run
POST /api/mcp-tools/mock_chikaya_submit/run
```

The LiveKit voice agent also exposes equivalent function tools directly to Gemini Live:

```text
route_hotline_issue
query_legal_knowledge_base
start_oral_approval_flow
confirm_oral_approval_flow
submit_mock_chikaya_complaint
```

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
