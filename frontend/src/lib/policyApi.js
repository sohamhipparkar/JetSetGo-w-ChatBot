// Talks to the JetSetGo policy chatbot backend (backend/server.py).
// In development Vite proxies /api to http://localhost:8000 (see vite.config.js).
// In production set VITE_API_URL to the deployed backend, e.g. https://jetsetgo-api.onrender.com

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export async function askPolicyBot(question, history = [], { signal } = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
      signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error(
      "Can't reach the policy assistant. Make sure the backend is running (python server.py in the backend folder)."
    );
  }
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) throw new Error(data.error || `The policy assistant returned an error (${res.status}).`);
  return data;
}

// Shared event so any page (e.g. Travel Policy) can open the chat with a question.
export const OPEN_CHAT_EVENT = "jetsetgo:open-chat";

export function openPolicyChat(question = "") {
  window.dispatchEvent(new CustomEvent(OPEN_CHAT_EVENT, { detail: { question } }));
}
