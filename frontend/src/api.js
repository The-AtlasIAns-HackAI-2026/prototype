export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "https://moulcyber.duckdns.org";

function workflowMeta(extra = {}) {
  return {
    channel: extra.channel || "web",
    trace_id: extra.traceId || `web-${Date.now()}`,
    caller_phone: extra.callerPhone || "",
    call_id: extra.callId || "",
  };
}

export async function fetchAnalytics() {
  const response = await fetch(`${API_BASE_URL}/api/analytics`);
  if (!response.ok) {
    throw new Error("Analytics request failed");
  }
  return response.json();
}

export async function sendChat(message, language = "darija") {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, language }),
  });
  if (!response.ok) {
    throw new Error("Chat request failed");
  }
  return response.json();
}

export async function triageHotline(message, language = "darija", providedFields = {}) {
  const meta = workflowMeta(providedFields);
  const response = await fetch(`${API_BASE_URL}/api/hotline/triage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, language, provided_fields: providedFields, ...meta }),
  });
  if (!response.ok) {
    throw new Error("Hotline triage request failed");
  }
  return response.json();
}

export async function submitMockChikaya(payload) {
  const response = await fetch(`${API_BASE_URL}/api/hotline/chikaya/mock-submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...workflowMeta(payload), ...payload, source: "mock-website" }),
  });
  if (!response.ok) {
    throw new Error("Mock Chikaya submit request failed");
  }
  return response.json();
}

export async function fetchMockChikayaSubmissions() {
  const response = await fetch(`${API_BASE_URL}/api/hotline/chikaya/mock-submissions`);
  if (!response.ok) {
    throw new Error("Mock Chikaya submissions request failed");
  }
  return response.json();
}

export async function queryLegalRag(question, options = {}) {
  const meta = workflowMeta(options);
  const response = await fetch(`${API_BASE_URL}/api/legal-rag/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      language: options.language || "darija",
      sector: options.sector || null,
      top_k: options.topK || 4,
      use_llm: options.useLlm ?? true,
      ...meta,
    }),
  });
  if (!response.ok) {
    throw new Error("Legal RAG request failed");
  }
  return response.json();
}

export async function fetchLegalRagStatus() {
  const response = await fetch(`${API_BASE_URL}/api/legal-rag/status`);
  if (!response.ok) {
    throw new Error("Legal RAG status request failed");
  }
  return response.json();
}

export async function buildCasePacket(payload) {
  const response = await fetch(`${API_BASE_URL}/api/hotline/case-packet`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...workflowMeta(payload), ...payload }),
  });
  if (!response.ok) {
    throw new Error("Case packet request failed");
  }
  return response.json();
}

export async function startOralApproval(action, summary) {
  const meta = workflowMeta();
  const response = await fetch(`${API_BASE_URL}/api/hotline/approval/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, summary, ...meta }),
  });
  if (!response.ok) {
    throw new Error("Approval start request failed");
  }
  return response.json();
}

export async function confirmOralApproval(approvalId, spokenText) {
  const meta = workflowMeta();
  const response = await fetch(`${API_BASE_URL}/api/hotline/approval/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, spoken_text: spokenText, ...meta }),
  });
  if (!response.ok) {
    throw new Error("Approval confirm request failed");
  }
  return response.json();
}
