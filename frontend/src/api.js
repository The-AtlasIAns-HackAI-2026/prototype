export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "https://moulcyber.duckdns.org";

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
  const response = await fetch(`${API_BASE_URL}/api/hotline/triage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, language, provided_fields: providedFields }),
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
    body: JSON.stringify({ ...payload, source: "mock-website" }),
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
  const response = await fetch(`${API_BASE_URL}/api/legal-rag/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      language: options.language || "darija",
      sector: options.sector || null,
      top_k: options.topK || 4,
      use_llm: options.useLlm ?? true,
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

export async function startOralApproval(action, summary) {
  const response = await fetch(`${API_BASE_URL}/api/hotline/approval/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, summary }),
  });
  if (!response.ok) {
    throw new Error("Approval start request failed");
  }
  return response.json();
}

export async function confirmOralApproval(approvalId, spokenText) {
  const response = await fetch(`${API_BASE_URL}/api/hotline/approval/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, spoken_text: spokenText }),
  });
  if (!response.ok) {
    throw new Error("Approval confirm request failed");
  }
  return response.json();
}
