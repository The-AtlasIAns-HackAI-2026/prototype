# LiveKit Migration

Main inbound path:

```text
Caller -> Twilio +17754060061 -> Twilio Elastic SIP Trunk -> LiveKit SIP -> Khadamati worker -> Gemini Live -> legal master -> sector RAG mini-agents
```

Configured IDs:

```text
Twilio trunk SID: TKc8fff9e36f81493855785cd5be5faff8
Twilio trunk domain: moulcyber-livekit.pstn.twilio.com
Twilio phone number SID: PNecb469b04a5df227099a520a8aed5900
Twilio origination URL SID: OU291a398dd8f2be3a4003845d967dd1b1
LiveKit project: moulcyber
LiveKit SIP URI: sip:0c0g2hzfv6c.sip.livekit.cloud
LiveKit inbound trunk ID: ST_N9CgGUScJL8y
LiveKit dispatch rule ID: SDR_FnGXiBPMwfKo
LiveKit agent name: moulcyber-live-agent (legacy dispatch name)
Gemini Live model: gemini-3.1-flash-live-preview
```

CLI verification on May 16, 2026:

```text
Twilio trunk domain is set.
Twilio origination URL points to LiveKit over TCP.
Twilio phone number is attached to the SIP trunk.
LiveKit inbound trunk and dispatch rule are active.
The local LiveKit agent is registered to LiveKit Cloud.
```

ElevenLabs remains in the backend as fallback only. The default provider is `VOICE_PROVIDER=livekit`, and Twilio webhooks return LiveKit SIP TwiML if they are used.

The LiveKit agent now exposes legal hotline orchestration tools to Gemini Live:

```text
route_hotline_issue
query_legal_knowledge_base
build_case_handoff_packet
start_oral_approval_flow
confirm_oral_approval_flow
submit_mock_chikaya_complaint
```

Those tools call the FastAPI backend at `HOTLINE_API_BASE_URL` and keep the voice path thin while the backend handles master-slave A2A routing, local legal RAG retrieval, missing-field collection, safety flags, oral approval, and mock Chikaya execution.

For latency, the voice agent calls `/api/legal-rag/query` with `use_llm=false`. Gemini Live then speaks from the retrieved chunks in the realtime session instead of waiting for a separate backend LLM response.

When the agent is thinking or waiting for tools, LiveKit publishes low-volume built-in hold music. Tool calls also log `channel`, `call_id`, masked caller phone, selected route, article, and latency through `/api/call-events`.

## Run

```bash
lk app env -w -d .env.livekit
docker compose up -d --build livekit-agent
docker compose logs --tail=100 livekit-agent
curl -fsS http://127.0.0.1:8081/
```

Then call:

```text
+1 775 406 0061
```

## MCP

MCP stays configurable at:

```text
config/mcp.servers.json
```

Legal hotline routing stays configurable at:

```text
config/hotline/experts.json
rag_datasets/
datasets/hotline/*.jsonl
```

Keep MCP enabled for the LiveKit agent with:

```text
MCP_ENABLED=true
MCP_SERVERS_FILE=/app/config/mcp.servers.json
```

Backend MCP-style tools:

```text
GET  /api/mcp-tools
POST /api/mcp-tools/hotline_route_issue/run
POST /api/mcp-tools/legal_rag_retrieve/run
POST /api/mcp-tools/case_packet_build/run
POST /api/mcp-tools/approval_flow_start/run
POST /api/mcp-tools/approval_flow_confirm/run
POST /api/mcp-tools/mock_chikaya_submit/run
```

The default Docker MCP config starts the local stdio server at:

```text
livekit_agent/mcp_stdio_server.py
```

That server exposes the Khadamati hotline tools as real MCP tools to LiveKit while proxying execution to the backend registry.

Example HTTP MCP server:

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
