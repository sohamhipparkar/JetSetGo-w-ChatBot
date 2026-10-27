"""Central configuration for the JetSetGo policy chatbot backend.

Values come from backend/.env. If GEMINI_API_KEY is not set there, the key in
frontend/.env is used as a fallback (it is only read here on the server; it is
never sent to the browser).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at import time so tests run without it
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent  # the JetSetGo folder
LOG_DIR = BACKEND_ROOT / "logs"

if load_dotenv is not None:
    load_dotenv(BACKEND_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "frontend" / ".env")  # does not override values already set

# One policy file, used by both the website's Travel Policy page and the chatbot.
DEFAULT_POLICY_PATH = Path(
    os.getenv("POLICY_PATH") or PROJECT_ROOT / "frontend" / "src" / "data" / "jetsetgo_policy.md"
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    api_key: str = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    temperature: float = float(os.getenv("TEMPERATURE", "0.1"))

    # Documents smaller than this (characters) are sent to the model in full, so
    # every clause is visible. Larger documents fall back to retrieval (top-k).
    full_context_char_limit: int = int(os.getenv("FULL_CONTEXT_CHAR_LIMIT", "120000"))
    top_k: int = int(os.getenv("TOP_K", "8"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "700"))

    # Second Gemini pass that checks every claim against the cited clauses.
    enable_llm_verifier: bool = _env_bool("ENABLE_LLM_VERIFIER", True)

    # Audit trail of every question, answer, citation and verdict.
    enable_audit_log: bool = _env_bool("ENABLE_AUDIT_LOG", True)

    company_name: str = os.getenv("COMPANY_NAME", "JetSetGo")
    support_contact: str = os.getenv(
        "SUPPORT_CONTACT", "JetSetGo Customer Care (support@jetsetgo.com, 1800-5555)"
    )


def get_settings() -> Settings:
    return Settings()
