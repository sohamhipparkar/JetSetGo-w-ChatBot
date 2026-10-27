"""PolicyAssistant: retrieval -> grounded answer -> verification -> safe reply."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import guardrails
from .chunker import Chunk, chunk_policy
from .config import LOG_DIR, Settings, get_settings
from .llm import GeminiLLM, LLMClient, LLMError
from .prompts import (
    ANSWER_SCHEMA,
    ANSWER_SYSTEM_PROMPT,
    ANSWER_USER_TEMPLATE,
    REPAIR_NOTE_TEMPLATE,
    VERIFIER_SCHEMA,
    VERIFIER_SYSTEM_PROMPT,
    VERIFIER_USER_TEMPLATE,
)
from .retriever import BM25Retriever

# Reply statuses
VERIFIED = "verified"
VERIFIED_WITH_CAVEATS = "verified_with_caveats"
NOT_IN_POLICY = "not_in_policy"
SAFE_MODE = "safe_mode"
BLOCKED = "blocked"
ERROR = "error"

STATUS_BADGES = {
    VERIFIED: "✅ Verified against policy",
    VERIFIED_WITH_CAVEATS: "🟡 Verified - check the conditions",
    NOT_IN_POLICY: "ℹ️ Not covered by the policy",
    SAFE_MODE: "🛡️ Showing exact policy text",
    BLOCKED: "⛔ Request not allowed",
    ERROR: "⚠️ Service error",
}


@dataclass
class CitedClause:
    chunk_id: str
    label: str
    quote: str
    clause_text: str


@dataclass
class AssistantReply:
    status: str
    answer: str
    citations: list[CitedClause] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    needs_human: bool = False
    confidence: str = "low"
    follow_up_question: str = ""
    verification: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def badge(self) -> str:
        return STATUS_BADGES.get(self.status, self.status)

    def to_dict(self) -> dict:
        return asdict(self)


class PolicyAssistant:
    def __init__(
        self,
        policy_text: str,
        policy_name: str = "policy document",
        llm: LLMClient | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.policy_name = policy_name
        self.policy_text = policy_text
        self.policy_hash = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:12]
        self.chunks: list[Chunk] = chunk_policy(policy_text, self.settings.chunk_size)
        if not self.chunks:
            raise ValueError("No usable text found in the policy document.")
        self.chunks_by_id = {c.id: c for c in self.chunks}
        self.retriever = BM25Retriever(self.chunks)
        self.full_context = len(policy_text) <= self.settings.full_context_char_limit
        self.llm = llm or GeminiLLM(self.settings.api_key, self.settings.model, self.settings.temperature)

    # ------------------------------------------------------------------ public

    def ask(self, question: str, history: list[dict] | None = None) -> AssistantReply:
        question = (question or "").strip()
        history = history or []
        if not question:
            return AssistantReply(status=ERROR, answer="Please type a question about the policy.")

        if guardrails.looks_like_injection(question):
            reply = AssistantReply(
                status=BLOCKED,
                answer=(
                    f"I can only answer questions about {self.settings.company_name}'s policies, using the "
                    "policy document. I can't change how I work. What would you like to know about the policy?"
                ),
            )
            self._audit(question, reply, [])
            return reply

        try:
            reply, problems = self._answer_with_verification(question, history)
        except LLMError as exc:
            reply, problems = AssistantReply(
                status=ERROR,
                answer=f"Sorry, I couldn't reach the language model right now. ({exc})",
                needs_human=True,
            ), [str(exc)]

        if guardrails.asks_for_decision(question) and reply.status not in (BLOCKED, ERROR):
            reply.needs_human = True

        if reply.needs_human and reply.status != ERROR:
            reply.notes.append(
                f"For a decision on your specific booking, please contact {self.settings.support_contact}. "
                "This assistant explains the written policy but cannot approve, refund or change bookings."
            )
        self._audit(question, reply, problems)
        return reply

    def outline(self) -> list[str]:
        seen, out = set(), []
        for c in self.chunks:
            if c.section_path and c.section_path[0] not in seen:
                seen.add(c.section_path[0])
                out.append(c.section_path[0])
        return out

    # ---------------------------------------------------------------- pipeline

    def _answer_with_verification(self, question: str, history: list[dict]) -> tuple[AssistantReply, list[str]]:
        last_user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
        retrieved = self.retriever.search(f"{question} {last_user}", self.settings.top_k)
        retrieved_chunks = [c for c, _ in retrieved]

        repair_note = ""
        problems: list[str] = []
        draft: dict = {}
        report = guardrails.CitationReport()
        verdict: dict = {}

        for attempt in range(2):  # first try + one repair try
            draft = self.llm.generate_json(
                ANSWER_SYSTEM_PROMPT.format(
                    company=self.settings.company_name,
                    support=self.settings.support_contact,
                    today=dt.date.today().isoformat(),
                ),
                self._build_prompt(question, history, retrieved_chunks, repair_note),
                ANSWER_SCHEMA,
            )
            problems = []
            answerable = bool(draft.get("answerable", False))
            answer_text = str(draft.get("answer", "")).strip()

            if not answerable:
                return self._not_in_policy(draft, retrieved_chunks), []

            report = guardrails.check_citations(draft.get("citations", []), self.chunks_by_id)
            for bad in report.invalid:
                problems.append(f"Citation {bad['chunk_id']} rejected: {bad['reason']} (quote: \"{bad['quote'][:120]}\")")
            if not report.valid:
                problems.append("The answer has no valid word-for-word citation from the policy.")

            promises = guardrails.find_promises(answer_text)
            if promises:
                problems.append(f"The answer makes promises on the airline's behalf: {promises}")

            verdict = {}
            if self.settings.enable_llm_verifier and report.valid:
                verdict = self._verify(question, draft, report, retrieved_chunks)
                v = verdict.get("verdict", "")
                if v in ("UNSUPPORTED", "CONTRADICTED"):
                    claims = "; ".join(verdict.get("problem_claims", [])) or verdict.get("explanation", "")
                    problems.append(f"Verifier verdict {v}: {claims}")
                if verdict.get("makes_unauthorized_promise"):
                    problems.append("Verifier: the answer makes an unauthorized promise.")

            if not problems:
                break
            repair_note = REPAIR_NOTE_TEMPLATE.format(problems="\n".join(f"- {p}" for p in problems))

        if problems:
            return self._safe_mode(report, retrieved_chunks, problems, verdict), problems

        partial = verdict.get("verdict") == "PARTIALLY_SUPPORTED" or bool(report.invalid)
        confidence = str(draft.get("confidence", "medium")).lower()
        if partial and confidence == "high":
            confidence = "medium"
        reply = AssistantReply(
            status=VERIFIED_WITH_CAVEATS if partial else VERIFIED,
            answer=str(draft.get("answer", "")).strip(),
            citations=self._cited(report.valid),
            conditions=[str(c) for c in draft.get("conditions", []) if str(c).strip()],
            needs_human=bool(draft.get("needs_human", False)),
            confidence=confidence,
            follow_up_question=str(draft.get("follow_up_question", "") or "").strip(),
            verification=verdict or {"verdict": "CITATIONS_CHECKED", "explanation": "LLM verifier disabled"},
        )
        if partial:
            reply.notes.append("Part of this answer could not be fully confirmed against the policy text - rely on the quoted clauses below.")
        return reply, []

    def _verify(self, question: str, draft: dict, report, retrieved: list[Chunk]) -> dict:
        ids = [c["chunk_id"] for c in report.valid] + [c.id for c in retrieved[:4]]
        clauses = "\n\n".join(self.chunks_by_id[i].render() for i in dict.fromkeys(ids) if i in self.chunks_by_id)
        try:
            return self.llm.generate_json(
                VERIFIER_SYSTEM_PROMPT,
                VERIFIER_USER_TEMPLATE.format(
                    clauses=clauses,
                    question=question,
                    answer=draft.get("answer", ""),
                    conditions="\n".join(f"- {c}" for c in draft.get("conditions", [])) or "(none)",
                ),
                VERIFIER_SCHEMA,
            )
        except LLMError as exc:
            return {"verdict": "UNVERIFIED", "explanation": f"Verifier unavailable: {exc}", "problem_claims": []}

    # ---------------------------------------------------------------- replies

    def _not_in_policy(self, draft: dict, retrieved: list[Chunk]) -> AssistantReply:
        answer = str(draft.get("answer", "")).strip() or "The policy document doesn't cover this question."
        reply = AssistantReply(
            status=NOT_IN_POLICY,
            answer=answer,
            needs_human=True,
            confidence="high",
            follow_up_question=str(draft.get("follow_up_question", "") or "").strip(),
            verification={"verdict": "NOT_IN_POLICY"},
        )
        # Never let a "not answerable" reply carry invented specifics.
        if guardrails.find_promises(answer):
            reply.answer = "The policy document doesn't cover this question, so I can't give you a reliable answer."
        reply.citations = [
            CitedClause(c.id, c.label, "", c.text) for c in retrieved[:2]
        ]
        if reply.citations:
            reply.notes.append("These clauses looked related, but they do not answer your exact question.")
        return reply

    def _safe_mode(self, report, retrieved: list[Chunk], problems: list[str], verdict: dict) -> AssistantReply:
        """Fallback when an answer can't be verified: show the policy's own words, nothing else."""
        source_ids = [c["chunk_id"] for c in report.valid] or [c.id for c in retrieved[:2]]
        source_ids = list(dict.fromkeys(source_ids))[:3]
        clauses = [self.chunks_by_id[i] for i in source_ids if i in self.chunks_by_id]
        answer = (
            "I want to be careful not to give you inaccurate information, so instead of summarising, "
            "here is exactly what the policy says on this topic. Please read the clauses below."
        )
        if not clauses:
            answer = "I couldn't produce an answer I can verify against the policy for this question."
        return AssistantReply(
            status=SAFE_MODE,
            answer=answer,
            citations=[CitedClause(c.id, c.label, "", c.text) for c in clauses],
            needs_human=True,
            confidence="low",
            verification=verdict or {"verdict": "FAILED_CHECKS"},
            notes=["The automated policy checker did not approve a summarised answer for this question."],
        )

    def _cited(self, valid: list[dict]) -> list[CitedClause]:
        out, seen = [], set()
        for cit in valid:
            key = (cit["chunk_id"], cit["quote"])
            if key in seen:
                continue
            seen.add(key)
            chunk = self.chunks_by_id[cit["chunk_id"]]
            out.append(CitedClause(chunk.id, chunk.label, cit["quote"], chunk.text))
        return out

    # ---------------------------------------------------------------- helpers

    def _build_prompt(self, question: str, history: list[dict], retrieved: list[Chunk], repair_note: str) -> str:
        if self.full_context:
            context_chunks = self.chunks
            mode = "complete document"
        else:
            # Retrieved clauses plus their neighbours (rules often continue in the next clause).
            ids = set()
            for c in retrieved:
                idx = self.chunks.index(c)
                ids.update(range(max(0, idx - 1), min(len(self.chunks), idx + 2)))
            context_chunks = [self.chunks[i] for i in sorted(ids)]
            mode = f"most relevant {len(context_chunks)} of {len(self.chunks)} clauses"
        context = "\n\n".join(c.render() for c in context_chunks)
        highlight = ", ".join(c.id for c in retrieved) or "(none found)"
        recent = history[-6:]
        hist = "\n".join(f"{m.get('role', 'user').upper()}: {str(m.get('content', ''))[:600]}" for m in recent) or "(none)"
        return ANSWER_USER_TEMPLATE.format(
            mode=mode, context=context, highlight=highlight, history=hist, question=question, repair_note=repair_note
        )

    def _audit(self, question: str, reply: AssistantReply, problems: list[str]) -> None:
        if not self.settings.enable_audit_log:
            return
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "policy": self.policy_name,
                "policy_hash": self.policy_hash,
                "question": question,
                "status": reply.status,
                "answer": reply.answer,
                "citations": [{"chunk_id": c.chunk_id, "quote": c.quote} for c in reply.citations],
                "verification": reply.verification,
                "rejected_draft_problems": problems,
                "needs_human": reply.needs_human,
            }
            with open(Path(LOG_DIR) / "audit_log.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # logging must never break the chat
