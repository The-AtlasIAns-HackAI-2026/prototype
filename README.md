# Khadamati

> **AI-powered legal hotline for rural Morocco — no smartphone, no internet required.**
> Just a phone call, in your own language.

---

## The Problem

Millions of Moroccans in rural areas face legal challenges every day — custody disputes, criminal accusations, eviction notices — with no access to a lawyer and no reliable internet. The information exists. The gap is delivery.

A phone line is all most people have. That's enough.

---

## What Khadamati Does

Dial **+1 775 406 0061** and speak naturally in **Moroccan Darija**. Khadamati listens, understands your situation, retrieves relevant articles from Moroccan law, and guides you — in real time, over a plain phone call.

No app. No data plan. No literacy barrier.

```
Caller (Darija): "Jani istid3a mn lmahkama w ma 3raftch deadline dyal listi2naf"
Khadamati:       Routes to civil_procedure sector
                 → Retrieves Article 134 (appeals deadline) from local RAG
                 → Speaks the answer back in clear, authentic Darija
                 → Builds a case packet for legal aid handoff
```

---

## Live Demo

| Channel | Access |
|---|---|
| Phone hotline | `+1 775 406 0061` |

---

## Architecture

```
  PSTN Caller (2G/landline)
         │
         ▼
   Twilio Elastic SIP Trunk
         │  SIP origination
         ▼
   LiveKit Cloud SIP
         │  dispatch room
         ▼
   LiveKit Agent (Python)
    ┌────┴─────────────────────────────────┐
    │  Gemini Live (realtime audio in/out) │
    │  GEMINI_THINKING_LEVEL=minimal       │
    └────┬─────────────────────────────────┘
         │  function tools
         ▼
   Legal Master Agent (A2A router)
    ├──► family_law mini-agent       ──► RAG chunks (65 articles)
    ├──► criminal_law mini-agent     ──► RAG chunks (430 articles)
    ├──► civil_procedure mini-agent  ──► RAG chunks (149 articles)
    ├──► constitutional_law agent    ──► RAG chunks (57 articles)
    ├──► public_finance agent        ──► RAG chunks (116 articles)
    └──► chikaya_complaints agent    ──► Mock Chikaya (oral approval gate)
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Telephony** | Twilio Elastic SIP Trunk | Reaches any PSTN phone |
| **Voice AI** | LiveKit + Gemini Live | Sub-second audio roundtrip, no STT/TTS cascade |
| **LLM** | Gemini 3.1 Flash | Best Darija/French code-switching; Google Search grounding |
| **Legal RAG** | Local FAISS-style retrieval + embeddings | Zero network call on the voice path — fast, private |
| **Tool Protocol** | MCP (Model Context Protocol) | Pluggable tools without re-deploying the agent |
| **A2A Orchestration** | Custom master → mini-agent topology | Each legal sector gets a specialized context window |
| **Backend** | FastAPI (Python) | Async, typed, Docker-ready |
| **Deployment** | Docker Compose + Nginx | DigitalOcean Droplet |

---

## Legal Knowledge Base

Five Moroccan legal documents, fully chunked and embedded locally:

| Sector | Source | Chunks |
|---|---|---|
| `family_law` | Family Law of Morocco | 65 |
| `constitutional_law` | Constitution of Morocco | 57 |
| `civil_procedure` | Civil Procedure Code | 149 |
| `criminal_law` | Moroccan Penal Code | 430 |
| `public_finance` | Finance Law 2026 | 116 |

Every RAG response exposes the nearest **article anchor** (`الفصل` / `المادة`) so the voice agent can cite the law by article number, not just paraphrase it.

---

## Key Features

### Voice-first, phone-first
Khadamati routes Twilio SIP calls directly into LiveKit, bypassing a separate STT + TTS cascade. Gemini Live handles everything in a single realtime session. Latency stays under one second even on the phone path.

### Authentic Moroccan Darija
Trained on real colloquial vocabulary — `maticha` not `tomatim`, `daba` not `alan`, `mzyan` not `jayyid`. No MSA. No Algerian dialect. The agent sounds like someone from the neighborhood, not a textbook.

### Agent-to-Agent (A2A) Legal Routing
A master legal agent classifies the caller's issue and delegates to the appropriate sector mini-agent. The A2A trace is visible in every RAG response — full auditability, no black-box routing.

### Oral Approval Gate
Before any action is filed (mock Chikaya complaint), the agent reads the full summary back to the caller and waits for the caller to say **"mwafeq"** (I agree). Consent is logged and required. Nothing is submitted without it.

### Case Packet for Human Handoff
After the call, Khadamati can produce a structured case packet — caller identity, selected expert, nearest legal article, evidence checklist, risk flags — ready for a legal aid organization or NGO to pick up.

### MCP Toolsets
The voice agent exposes six function tools to Gemini Live, mirrored as MCP endpoints for the backend:

```
route_hotline_issue          →  classify & triage the caller's legal problem
query_legal_knowledge_base   →  local RAG retrieval (no extra LLM call on voice path)
build_case_handoff_packet    →  structured packet for legal aid handoff
start_oral_approval_flow     →  read action summary, await verbal consent
confirm_oral_approval_flow   →  validate "mwafeq" phrase, log approval
submit_mock_chikaya_complaint →  mock complaint filing with audit receipt
```

---

## Project Structure

```
khadamati/
├── backend/
│   ├── main.py              ← FastAPI: all routes, RAG, hotline, MCP, Twilio
│   ├── legal_rag.py         ← Local retrieval engine + article anchoring
│   ├── hotline_engine.py    ← A2A router, oral approval, mock Chikaya
│   ├── mcp_tools.py         ← MCP tool registry
│   ├── logger.py            ← Anonymized JSONL event logging
│   └── languages.py         ← Darija / French prompt config
├── livekit_agent/
│   ├── agent.py             ← LiveKit worker: Gemini Live + function tools + MCP
│   └── mcp_stdio_server.py  ← Local stdio MCP server bridging agent ↔ backend
├── frontend/                ← React/Vite dashboard
├── rag_datasets/            ← Chunked PDFs + embeddings (per sector)
├── config/
│   ├── hotline/experts.json ← A2A topology: master + mini-agents + datasets
│   └── mcp.servers.json     ← MCP server config
├── prompts/                 ← Darija + French system prompts
└── docker-compose.yml
```

---

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
lk app env -w -d .env.livekit   # pull LiveKit credentials

# 2. Start services
docker compose up -d --build

# 3. Verify
curl -fsS http://127.0.0.1:7331/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "khadamati",
  "voice_provider": "livekit",
  "calls_ready": true,
  "hotline_ready": true,
  "legal_rag_ready": true
}
```

---

## Try the API

```bash
# Ask a legal question in Darija (local RAG, no LLM call)
curl -X POST http://127.0.0.1:7331/api/legal-rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chno kaygol qanoun lmaghribi 3la l7adana ba3d talaq?","language":"darija","top_k":3,"use_llm":false}'

# Triage a hotline issue
curl -X POST http://127.0.0.1:7331/api/hotline/triage \
  -H 'Content-Type: application/json' \
  -d '{"message":"Jani istid3a mn lmahkama w ma 3raftch deadline dyal listi2naf","language":"darija"}'

# See all expert mini-agents
curl http://127.0.0.1:7331/api/hotline/experts

# See all MCP tools
curl http://127.0.0.1:7331/api/mcp-tools
```

---

## Required Environment Variables

```env
# LiveKit voice path
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
GOOGLE_API_KEY=

# Backend text/chat
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite

# Twilio (for phone number routing)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=+17754060061
```

See `.env.example` for the full list.

---

## Hackathon Demo Path
Just call **+1 775 406 0061** and speak in Darija.

---

## Why This Matters

Morocco has ~37 million people. Millions live in rural areas where the nearest legal clinic might be hours away and internet access is a luxury. The justice gap is not a knowledge problem — the laws exist, they're public, they apply to everyone. The gap is access.

A phone call costs almost nothing. Khadamati turns any line into a legal aid hotline, available 24/7, that speaks your language, cites the actual law, and knows when to escalate to a human.

---

## Built at HackAI 2026 · AI for Rural Areas
