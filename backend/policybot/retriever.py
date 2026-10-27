"""Dependency-free BM25 retriever with airline-specific query expansion.

Used to (a) rank clauses for large documents that don't fit in the prompt and
(b) highlight the most relevant clauses even in full-context mode.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .chunker import Chunk

STOPWORDS = set(
    """a an the and or but if of to in on at for from by with about as is are was were be been being
    do does did can could should would will shall may might must i me my we our you your it its this that
    these those there here what which who whom how when where why am have has had not no so than then
    any all some please tell know want get""".split()
)

# Customers rarely use the words a policy uses. Expand both ways.
SYNONYMS: dict[str, list[str]] = {
    "refund": ["refund", "refundable", "reimbursement", "money", "back", "credit"],
    "cancel": ["cancel", "cancellation", "cancelled", "canceled"],
    "change": ["change", "modify", "modification", "reschedule", "rebook", "amend"],
    "bereavement": ["bereavement", "compassionate", "death", "funeral", "deceased", "family"],
    "death": ["bereavement", "compassionate", "death", "deceased", "funeral"],
    "funeral": ["bereavement", "compassionate", "funeral", "death"],
    "baggage": ["baggage", "bag", "bags", "luggage", "checked", "carry"],
    "luggage": ["baggage", "bag", "luggage", "checked"],
    "bag": ["baggage", "bag", "luggage"],
    "delay": ["delay", "delayed", "late", "disruption", "compensation"],
    "late": ["delay", "delayed", "late"],
    "compensation": ["compensation", "delay", "denied", "boarding", "voucher"],
    "pet": ["pet", "pets", "animal", "dog", "cat", "service"],
    "dog": ["pet", "animal", "dog"],
    "child": ["child", "children", "minor", "infant", "unaccompanied", "kid"],
    "kid": ["child", "children", "minor", "infant"],
    "baby": ["infant", "child", "baby"],
    "name": ["name", "correction", "passenger", "transfer"],
    "wheelchair": ["wheelchair", "assistance", "disability", "mobility", "special"],
    "overbooked": ["overbooking", "denied", "boarding", "oversold"],
    "noshow": ["show", "no-show", "missed"],
    "missed": ["missed", "no-show", "show"],
    "seat": ["seat", "seats", "selection"],
    "pay": ["payment", "pay", "card", "currency"],
    "fee": ["fee", "fees", "charge", "cost", "price"],
    "cost": ["fee", "charge", "cost", "price"],
    "chatbot": ["chatbot", "assistant", "automated", "digital", "information"],
    "voucher": ["voucher", "credit", "travel"],
    "retroactive": ["retroactive", "retroactively", "after", "travel", "completed"],
    "after": ["after", "retroactive", "completed"],
    "died": ["bereavement", "compassionate", "death", "deceased"],
    "passed": ["bereavement", "death", "deceased"],
    "dying": ["bereavement", "imminent", "death"],
    "grandmother": ["bereavement", "grandparent", "family"],
    "grandfather": ["bereavement", "grandparent", "family"],
    "mother": ["bereavement", "parent", "family"],
    "father": ["bereavement", "parent", "family"],
    "infant": ["infant", "lap", "child"],
    "alone": ["unaccompanied", "minor", "alone"],
    "lost": ["lost", "baggage", "claim"],
    "damaged": ["damaged", "baggage", "claim"],
    "hotel": ["hotel", "accommodation", "overnight"],
    "complaint": ["complaint", "complaints", "claim", "customer", "care"],
    "contact": ["customer", "care", "contact", "phone", "email"],
}


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(t) for t in tokens if t not in STOPWORDS and len(t) > 1]


def _stem(token: str) -> str:
    for suffix in ("ations", "ation", "ments", "ment", "ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


def expand_query(query: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", query.lower())
    expanded = list(raw)
    for word in raw:
        expanded.extend(SYNONYMS.get(word, []))
        expanded.extend(SYNONYMS.get(_stem(word), []))
    return [_stem(t) for t in expanded if t not in STOPWORDS and len(t) > 1]


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        # Index heading text too (weighted x2) - headings are strong signals.
        self.docs = [tokenize(f"{c.label} {c.label} {c.text}") for c in chunks]
        self.doc_len = [len(d) for d in self.docs]
        self.avgdl = (sum(self.doc_len) / len(self.docs)) if self.docs else 0.0
        self.tf = [Counter(d) for d in self.docs]
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, top_k: int = 8) -> list[tuple[Chunk, float]]:
        terms = expand_query(query)
        if not terms or not self.chunks:
            return []
        weights = Counter(terms)
        scores = []
        for i, tf in enumerate(self.tf):
            score = 0.0
            for term, qw in weights.items():
                if term not in tf:
                    continue
                f = tf[term]
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
                score += self.idf.get(term, 0.0) * (f * (self.k1 + 1) / denom) * (1 + 0.2 * (qw - 1))
            if score > 0:
                scores.append((self.chunks[i], score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
