import React from "react";

/**
 * Tiny, safe Markdown renderer for chatbot answers.
 * Supports paragraphs, "- " / "* " / "1. " lists, **bold** and *italic*.
 * It builds React elements (never raw HTML), so model output cannot inject markup.
 */

function renderInline(text, keyPrefix) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    parts.push(
      token.startsWith("**") ? (
        <strong key={`${keyPrefix}-${i++}`} className="font-semibold text-gray-900">{token.slice(2, -2)}</strong>
      ) : (
        <em key={`${keyPrefix}-${i++}`}>{token.slice(1, -1)}</em>
      )
    );
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function parseBlocks(text) {
  const blocks = [];
  let para = null;
  let list = null;

  for (const raw of String(text || "").replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const numbered = line.match(/^(\d+)[.)]\s+(.*)$/);

    if (!line) {          // blank line ends the current paragraph / list
      para = null;
      list = null;
      continue;
    }
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        list = { type, items: [] };
        blocks.push(list);
      }
      list.items.push(bullet ? bullet[1] : numbered[2]);
      para = null;
      continue;
    }
    list = null;
    if (para) para.text += " " + line;
    else {
      para = { type: "p", text: line };
      blocks.push(para);
    }
  }
  return blocks;
}

export default function MiniMarkdown({ text, className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {parseBlocks(text).map((b, bi) => {
        if (b.type === "p") return <p key={bi}>{renderInline(b.text, `p${bi}`)}</p>;
        const Tag = b.type;
        return (
          <Tag key={bi} className={`${b.type === "ul" ? "list-disc" : "list-decimal"} pl-5 space-y-1`}>
            {b.items.map((item, ii) => (
              <li key={ii}>{renderInline(item, `l${bi}-${ii}`)}</li>
            ))}
          </Tag>
        );
      })}
    </div>
  );
}
