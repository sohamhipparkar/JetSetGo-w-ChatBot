"""JetSetGo policy chatbot API.

The same verified pipeline as the Flight Policy Assistant (policybot), served
over HTTP for the React website.

Run:  python server.py          -> http://localhost:8000

Endpoints
  GET  /api/health   status, model and policy info
  POST /api/chat     {"question": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request

from policybot.config import DEFAULT_POLICY_PATH, get_settings
from policybot.engine import STATUS_BADGES, PolicyAssistant
from policybot.llm import LLMError
from policybot.loader import load_policy

MAX_QUESTION_CHARS = 1000
MAX_HISTORY_TURNS = 8
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
}

app = Flask(__name__)

_assistant: PolicyAssistant | None = None
_assistant_error: str | None = None
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def get_assistant() -> PolicyAssistant:
    """Build the assistant once (lazily, so /api/health works even without a key)."""
    global _assistant, _assistant_error
    if _assistant is None:
        with _lock:
            if _assistant is None:
                try:
                    _assistant = PolicyAssistant(
                        load_policy(DEFAULT_POLICY_PATH), policy_name="JetSetGo travel policy", settings=get_settings()
                    )
                    _assistant_error = None
                except (LLMError, ValueError) as exc:
                    _assistant_error = str(exc)
                    raise
    return _assistant


def set_assistant(assistant: PolicyAssistant | None) -> None:
    """Used by tests to inject an assistant with a fake LLM."""
    global _assistant
    _assistant = assistant


# --------------------------------------------------------------------- helpers

SECTION_NUM_RE = re.compile(r"^(\d+)\.\s")


def _section_anchor(label: str) -> str:
    """'JetSetGo - ... > 7. Bereavement ...' -> 'section-7' (matches the Travel Policy page ids)."""
    for part in reversed(label.split(" > ")):
        m = SECTION_NUM_RE.match(part.strip())
        if m:
            return f"section-{m.group(1)}"
    return ""


def _display_label(label: str) -> str:
    parts = label.split(" > ")
    return " > ".join(parts[1:]) if len(parts) > 1 else label


def serialize(reply) -> dict:
    data = reply.to_dict()
    data["badge"] = STATUS_BADGES.get(reply.status, reply.status)
    for cit in data["citations"]:
        cit["anchor"] = _section_anchor(cit["label"])
        cit["label"] = _display_label(cit["label"])
    return data


def _rate_limited(ip: str) -> bool:
    now = time.time()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        return True
    window.append(now)
    return False


def _clean_history(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    history = []
    for item in raw[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content", ""))[:2000]
        if role in ("user", "assistant") and content.strip():
            history.append({"role": role, "content": content})
    return history


# ------------------------------------------------------------------------ CORS

@app.after_request
def add_cors(response):
    origin = request.headers.get("Origin")
    if origin and (origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ---------------------------------------------------------------------- routes

@app.get("/api/health")
def health():
    settings = get_settings()
    info = {
        "status": "ok",
        "model": settings.model,
        "api_key_configured": bool(settings.api_key and not settings.api_key.startswith("your_")),
        "policy_file": DEFAULT_POLICY_PATH.name,
    }
    try:
        a = get_assistant()
        info.update(clauses=len(a.chunks), policy_hash=a.policy_hash, verifier=a.settings.enable_llm_verifier)
    except Exception as exc:  # noqa: BLE001
        info.update(status="not_ready", error=str(exc))
    return jsonify(info)


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return ("", 204)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    if _rate_limited(ip):
        return jsonify(error="Too many questions in a short time. Please wait a minute and try again."), 429

    body = request.get_json(silent=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify(error="Please type a question about the JetSetGo travel policy."), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify(error=f"Please keep your question under {MAX_QUESTION_CHARS} characters."), 400

    try:
        assistant = get_assistant()
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=f"The policy assistant is not available: {exc}"), 503

    reply = assistant.ask(question, _clean_history(body.get("history")))
    return jsonify(serialize(reply))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"JetSetGo policy chatbot API on http://localhost:{port}  (policy: {DEFAULT_POLICY_PATH})")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
