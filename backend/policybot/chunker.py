"""Split a policy document into citable clauses.

Each chunk keeps its section heading and (for PDFs) its page number, so every
answer can point the customer to the exact clause it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PAGE_RE = re.compile(r"^\[\[PAGE (\d+)\]\]$")
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# "4. Refunds", "4.2 Refund eligibility", "Section 7 - Baggage", "Article 3: Fares"
NUMBERED_HEADING_RE = re.compile(
    r"^((?:section|article|clause|part)\s+\d+[\w.]*|\d+(?:\.\d+){0,3}\.?)\s*[-:.)]?\s+([A-Z].{2,90})$",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    id: str
    heading: str
    text: str
    page: int | None = None
    section_path: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        where = " > ".join(self.section_path) or self.heading or "Document"
        return f"{where} (p. {self.page})" if self.page else where

    def render(self) -> str:
        return f"[{self.id}] {self.label}\n{self.text}"


def _is_caps_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return (
        4 <= len(line) <= 80
        and len(letters) >= 4
        and all(c.isupper() for c in letters)
        and not line.endswith(".")
    )


def _detect_heading(line: str) -> tuple[int, str] | None:
    """Return (level, title) if the line looks like a heading."""
    m = MD_HEADING_RE.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip()
    m = NUMBERED_HEADING_RE.match(line)
    if m and len(line) <= 100 and not line.rstrip().endswith((".", ";", ",")):
        number = m.group(1).rstrip(".")
        level = number.count(".") + 2 if number[0].isdigit() else 2
        return min(level, 6), line.strip()
    if _is_caps_heading(line):
        return 2, line.strip().title()
    return None


def chunk_policy(text: str, max_chars: int = 1200) -> list[Chunk]:
    sections: list[tuple[list[str], int | None, list[str]]] = []
    path: list[tuple[int, str]] = []
    current_lines: list[str] = []
    page: int | None = None
    section_page: int | None = None

    def flush():
        body = "\n".join(current_lines).strip()
        if body:
            sections.append(([t for _, t in path], section_page, body.split("\n")))
        current_lines.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        page_match = PAGE_RE.match(line)
        if page_match:
            page = int(page_match.group(1))
            if not current_lines:
                section_page = page
            continue
        heading = _detect_heading(line) if line else None
        if heading:
            flush()
            level, title = heading
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
            section_page = page
            continue
        if not current_lines:
            section_page = page
        current_lines.append(raw.rstrip())
    flush()

    chunks: list[Chunk] = []
    for section_path, sec_page, lines in sections:
        for piece in _split_long("\n".join(lines), max_chars):
            chunks.append(
                Chunk(
                    id=f"C{len(chunks) + 1:03d}",
                    heading=section_path[-1] if section_path else "",
                    text=piece,
                    page=sec_page,
                    section_path=section_path,
                )
            )
    return chunks


def _split_long(body: str, max_chars: int) -> list[str]:
    if len(body) <= max_chars:
        return [body.strip()]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\s*[-*•]|\s*\(?[a-z0-9]\))", body) if p.strip()]
    pieces, buf = [], ""
    for para in paragraphs:
        if len(para) > max_chars:  # very long paragraph -> split on sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
        else:
            sentences = [para]
        for sent in sentences:
            if buf and len(buf) + len(sent) + 1 > max_chars:
                pieces.append(buf.strip())
                buf = ""
            buf = f"{buf}\n{sent}" if buf else sent
    if buf.strip():
        pieces.append(buf.strip())
    return pieces
