# Khadamati Setup Steps

The legal hotline is now the main product. LiveKit + Gemini Live is the main call path; ElevenLabs stays available as an explicit fallback, but it is no longer the default route.

## 1. Environment

```bash
cp .env.example .env
lk app env -w -d .env.livekit
```

Required for LiveKit calls:

```text
VOICE_PROVIDER=livekit
LIVEKIT_SIP_URI=sip:0c0g2hzfv6c.sip.livekit.cloud;transport=tcp
HOTLINE_API_BASE_URL=http://backend:8000
HOTLINE_EXPERTS_FILE=/app/config/hotline/experts.json
MOCK_CHIKAYA_LOG_FILE=/app/logs/mock_chikaya_submissions.jsonl
ORAL_APPROVAL_LOG_FILE=/app/logs/oral_approvals.jsonl
LEGAL_RAG_DIR=/app/rag_datasets
GOOGLE_API_KEY=...
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_THINKING_LEVEL=minimal
MCP_ENABLED=true
```

Required for `/api/chat`:

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash
LLM_FALLBACK_ON_ERROR=true
```

Required only for `/api/calls/outbound`:

```text
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
```

## 2. Twilio SIP Trunk

Confirmed by CLI on May 16, 2026:

```text
Trunk name: moulcyber-livekit
Trunk domain: moulcyber-livekit.pstn.twilio.com
Origination URL: sip:0c0g2hzfv6c.sip.livekit.cloud;transport=tcp
Phone number: +17754060061
```

Verify when needed:

```bash
twilio api:trunking:v1:trunks:list --properties sid,friendlyName,domainName
twilio api:trunking:v1:trunks:origination-urls:list --trunk-sid TKc8fff9e36f81493855785cd5be5faff8
twilio api:trunking:v1:trunks:phone-numbers:list --trunk-sid TKc8fff9e36f81493855785cd5be5faff8
```

## 3. LiveKit SIP

Confirmed by CLI:

```text
Project: moulcyber
Inbound trunk: ST_N9CgGUScJL8y
Dispatch rule: SDR_FnGXiBPMwfKo
Agent: moulcyber-live-agent (legacy dispatch name)
```

Verify when needed:

```bash
lk sip inbound list
lk sip dispatch list
docker compose logs --tail=100 livekit-agent
```

## 4. Start Services

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:7331/health
curl -fsS http://127.0.0.1:8081/
```

Expected backend health includes:

```json
{
  "voice_provider": "livekit",
  "calls_ready": true,
  "livekit_ready": true,
  "hotline_ready": true,
  "legal_rag_ready": true
}
```

## 5. Legal RAG

The legal RAG datasets are mounted from:

```text
rag_datasets/
rag_datasets/sectors/*/chunks.jsonl
rag_datasets/sectors/*/embeddings.npy
```

Useful checks:

```bash
curl -fsS http://127.0.0.1:7331/api/legal-rag/status

curl -fsS -X POST http://127.0.0.1:7331/api/legal-rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chno kaygol qanoun lmaghribi 3la l7adana ba3d talaq?","language":"darija","top_k":3,"use_llm":false}'

curl -fsS -X POST http://127.0.0.1:7331/api/legal-rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Chno l3o9oba dyal sari9a f lqanoun jinai?","language":"darija","top_k":3,"use_llm":false}'
```

Use `use_llm=false` for the fastest path. The LiveKit voice agent passes those retrieved sources into Gemini Live instead of asking the backend to do another slow model call.

## 6. Hotline Lab And MCP

The hotline engine is configured at:

```text
config/hotline/experts.json
datasets/hotline/*.jsonl
```

Useful checks:

```bash
curl -fsS http://127.0.0.1:7331/api/hotline/experts
curl -fsS http://127.0.0.1:7331/api/mcp-tools

curl -fsS -X POST http://127.0.0.1:7331/api/mcp-tools/approval_flow_start/run \
  -H 'Content-Type: application/json' \
  -d '{"payload":{"action":"mock_chikaya_submit","summary":"Voice caller asks to file a mock complaint after review."}}'
```

Open the frontend `Hotline` tab to test:

```text
Legal RAG -> A2A trace -> oral approval -> mwafeq confirmation -> mock Chikaya submit -> audit receipt
```

## 7. ElevenLabs Fallback

To switch back later, set:

```text
VOICE_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_AGENT_ID=...
```

Then route Twilio to:

```text
https://moulcyber.duckdns.org/twilio/inbound
```

## 8. Frontend

When Vercel is ready:

```text
VITE_API_BASE_URL=https://moulcyber.duckdns.org
VITE_SHOW_ELEVENLABS_WIDGET=false
```
