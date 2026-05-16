# LiveKit Migration

Main inbound path:

```text
Caller -> Twilio +17754060061 -> Twilio Elastic SIP Trunk -> LiveKit SIP -> moulcyber-live-agent -> Gemini Live
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
LiveKit agent name: moulcyber-live-agent
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

Keep MCP enabled for the LiveKit agent with:

```text
MCP_ENABLED=true
MCP_SERVERS_FILE=/app/config/mcp.servers.json
```

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
