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
