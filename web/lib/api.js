// Thin wrapper around the FastAPI backend. One function per endpoint, no abstraction beyond
// that -- this app has one API to talk to.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = new Error(`${options?.method || "GET"} ${path} -> ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

export function listCustomers() {
  return request("/customers");
}

export function sendChat(message, customerId) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ message, customer_id: customerId || null }),
  });
}

export function getMemories(customerId) {
  return request(`/memories?customer_id=${customerId}`);
}

export function getRetrieval(messageId, customerId) {
  return request(`/retrieval/${messageId}?customer_id=${customerId}`);
}

export function getOpsMetrics() {
  return request("/ops/metrics");
}

export function endConversation(customerId) {
  return request("/conversations/end", {
    method: "POST",
    body: JSON.stringify({ customer_id: customerId }),
  });
}

// --- FR-7 governance actions (design brief §3.2, §11), implemented in S6.

export function correctMemory(memoryId, customerId) {
  return request(`/memories/${memoryId}?customer_id=${customerId}`, {
    method: "PATCH",
    body: JSON.stringify({ action: "correct" }),
  });
}

export function forgetMemory(memoryId, customerId) {
  return request(`/memories/${memoryId}?customer_id=${customerId}`, { method: "DELETE" });
}

export function forgetEverything(customerId) {
  return request(`/memories?customer_id=${customerId}`, { method: "DELETE" });
}

export function downloadDataUrl(customerId) {
  return `${API_BASE}/memories/export?customer_id=${customerId}`;
}

export function withdrawConsent(customerId) {
  return request("/consents/withdraw", {
    method: "POST",
    body: JSON.stringify({ customer_id: customerId }),
  });
}
