"""Deterministic safety checks that run around the LLM.

These are the layers that stop an "Air Canada chatbot" answer from reaching a
customer: fake citations, invented quotes, binding promises and prompt
injection are all caught without trusting the model to police itself.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .chunker import Chunk

# ---------------------------------------------------------------- citations


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = (
        text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
    )
    text = re.sub(r"[*_`#>]", "", text)  # markdown emphasis in the source
    text = re.sub(r"[^\w%$€£₹'\-./ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_in_chunk(quote: str, chunk: Chunk) -> bool:
    """True if the quote appears verbatim (after normalisation) in the clause.

    Quotes with an ellipsis are accepted when every fragment appears, in order.
    """
    source = normalize(chunk.text)
    fragments = [normalize(f) for f in re.split(r"\.\.\.|…", quote)]
    fragments = [f.strip(" .") for f in fragments if len(f.strip(" .")) >= 3]
    if not fragments:
        return False
    position = 0
    for fragment in fragments:
        found = source.find(fragment, position)
        if found == -1:
            return False
        position = found + len(fragment)
    return True


@dataclass
class CitationReport:
    valid: list[dict] = field(default_factory=list)
    invalid: list[dict] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return not self.invalid


def check_citations(citations: list[dict], chunks_by_id: dict[str, Chunk]) -> CitationReport:
    report = CitationReport()
    for cit in citations or []:
        chunk_id = str(cit.get("chunk_id", "")).strip().strip("[]").upper()
        quote = str(cit.get("quote", "")).strip().strip('"')
        chunk = chunks_by_id.get(chunk_id)
        entry = {"chunk_id": chunk_id, "quote": quote}
        if chunk is None:
            entry["reason"] = "clause id does not exist"
            report.invalid.append(entry)
        elif not quote_in_chunk(quote, chunk):
            entry["reason"] = "quote is not word-for-word in the clause"
            report.invalid.append(entry)
        else:
            report.valid.append(entry)
    return report


# ------------------------------------------------------- binding promises

PROMISE_PATTERNS = [
    r"\bi (?:have|'ve) (?:approved|processed|issued|refunded|waived|booked|cancelled|canceled)\b",
    r"\bi (?:will|'ll|can) (?:approve|process|issue|refund|waive|guarantee|authori[sz]e|make an exception)\b",
    r"\b(?:we|i) guarantee\b",
    r"\bguaranteed (?:a |to )?(?:refund|approval|compensation)\b",
    r"\byou will (?:definitely |certainly |surely )?(?:get|receive|be (?:given|issued|refunded|reimbursed|compensated))\b",
    r"\byour (?:refund|request|claim|exception) (?:has been|is) (?:approved|processed|granted)\b",
    r"\bconsider (?:it|this) (?:done|approved)\b",
]
_PROMISE_RE = re.compile("|".join(PROMISE_PATTERNS), re.IGNORECASE)


def find_promises(answer: str) -> list[str]:
    return [m.group(0) for m in _PROMISE_RE.finditer(answer or "")]


# ------------------------------------------------------- prompt injection

INJECTION_PATTERNS = [
    r"(?:ignore|forget|disregard|override|bypass) (?:all |any |the |your |of your )*(?:previous |prior |above |earlier |system )*(?:instructions|rules|prompts?|guidelines)",
    r"(?:ignore|forget|disregard) your polic(?:y|ies)",
    r"(?:reveal|show|print|repeat) (?:me )?(?:your|the) (?:system )?(?:prompt|instructions)",
    r"you are now\b",
    r"you're now\b",
    r"pretend (?:to be|you are|you're|that you are)",
    r"role-?play as",
    r"act as (?:if|an?)\b",
    r"developer mode",
    r"jailbreak",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def looks_like_injection(message: str) -> bool:
    return bool(_INJECTION_RE.search(message or ""))


# Customer asks the bot itself to decide or commit on their booking.
DECISION_PATTERNS = [
    r"\b(?:approve|authori[sz]e|confirm|promise|guarantee) (?:my|me|that i|a|the) (?:refund|claim|exception|request|compensation)",
    r"\bpromise me\b",
    r"\bcan you (?:refund|cancel|rebook|change) my\b",
    r"\b(?:booking|pnr|confirmation) (?:number|code|ref(?:erence)?)\b",
]
_DECISION_RE = re.compile("|".join(DECISION_PATTERNS), re.IGNORECASE)


# A booking reference such as "ABC123" (upper-case letters + digits, 5-8 chars).
_PNR_RE = re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{5,8}\b")


def asks_for_decision(message: str) -> bool:
    message = message or ""
    return bool(_DECISION_RE.search(message) or _PNR_RE.search(message))
