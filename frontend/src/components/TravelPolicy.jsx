import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { BookOpen, ChevronRight, Info, MessageCircle, Search, ShieldCheck, X } from "lucide-react";
import Navbar from "./Navbar";
import Footer from "./Footer";
import policyText from "../data/jetsetgo_policy.md?raw";
import { openPolicyChat } from "../lib/policyApi";

/*
 * Renders the JetSetGo Booking, Fare and Travel Policy.
 * This is the SAME file the chatbot answers from (backend reads frontend/src/data/jetsetgo_policy.md),
 * so the website and the chatbot can never disagree.
 * Section ids (#section-7) match the links in the chatbot's citations.
 */

function parsePolicy(text) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let title = "";
  const intro = [];
  const sections = [];
  let current = null;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("# ")) {
      title = line.slice(2).trim();
    } else if (line.startsWith("## ")) {
      const heading = line.slice(3).trim();
      const m = heading.match(/^(\d+)\.\s*(.*)$/);
      current = { num: m ? m[1] : String(sections.length + 1), title: m ? m[2] : heading, clauses: [] };
      sections.push(current);
    } else if (current) {
      const m = line.match(/^(\d+\.\d+)\s+(.*)$/);
      if (m) current.clauses.push({ num: m[1], text: m[2] });
      else if (current.clauses.length) current.clauses[current.clauses.length - 1].text += " " + line;
      else current.clauses.push({ num: "", text: line });
    } else {
      intro.push(line);
    }
  }
  return { title, intro, sections };
}

function Highlight({ text, query }) {
  if (!query) return text;
  const safe = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${safe})`, "ig"));
  return parts.map((p, i) =>
    p.toLowerCase() === query.toLowerCase() ? (
      <mark key={i} className="rounded bg-amber-200 px-0.5 text-gray-900">{p}</mark>
    ) : (
      <React.Fragment key={i}>{p}</React.Fragment>
    )
  );
}

const SECTION_QUESTIONS = {
  2: "What are the differences between the fare types?",
  4: "How does the 24-hour risk-free cancellation work?",
  6: "When can I get a refund if I cancel?",
  7: "How do bereavement fares work, and when must I request one?",
  8: "What is the baggage allowance and what do extra bags cost?",
  9: "What am I entitled to if my flight is delayed?",
};

export default function TravelPolicy() {
  const { title, intro, sections } = useMemo(() => parsePolicy(policyText), []);
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState("");
  const location = useLocation();

  const q = query.trim();
  const visible = useMemo(() => {
    if (!q) return sections;
    const needle = q.toLowerCase();
    return sections
      .map((s) => ({
        ...s,
        clauses: s.title.toLowerCase().includes(needle) ? s.clauses : s.clauses.filter((c) => c.text.toLowerCase().includes(needle)),
      }))
      .filter((s) => s.clauses.length);
  }, [q, sections]);

  // Scroll to #section-N (used by the chatbot's citation links) and flash it.
  useEffect(() => {
    if (!location.hash) return;
    const id = location.hash.slice(1);
    setQuery("");
    const t = setTimeout(() => {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        setActiveId(id);
        setTimeout(() => setActiveId(""), 2400);
      }
    }, 120);
    return () => clearTimeout(t);
  }, [location.hash]);

  const matchCount = q ? visible.reduce((n, s) => n + s.clauses.length, 0) : 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      {/* Hero */}
      <div className="relative overflow-hidden bg-gradient-to-r from-indigo-900 via-blue-800 to-indigo-800 px-4 pb-20 pt-12">
        <div className="absolute right-0 top-0 h-96 w-96 -translate-y-1/2 translate-x-1/3 rounded-full bg-white opacity-10 blur-3xl" />
        <div className="absolute bottom-0 left-0 h-96 w-96 -translate-x-1/3 translate-y-1/2 rounded-full bg-indigo-300 opacity-10 blur-3xl" />
        <div className="relative mx-auto max-w-4xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-blue-100 ring-1 ring-white/20">
            <BookOpen className="h-3.5 w-3.5" /> Official policy
          </span>
          <h1 className="mt-4 text-4xl font-bold text-white md:text-5xl">{title.replace(/^JetSetGo\s*-\s*/, "") || "Travel Policy"}</h1>
          <p className="mt-3 text-indigo-100">{intro.join(" ")}</p>

          <div className="mx-auto mt-8 flex max-w-2xl flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search the policy (e.g. refund, baggage, infant)"
                className="w-full rounded-xl border-0 py-3.5 pl-12 pr-10 text-gray-800 shadow-lg focus:ring-4 focus:ring-indigo-300"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-1 text-gray-400 hover:bg-gray-100"
                  aria-label="Clear search"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => openPolicyChat()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3.5 font-semibold text-indigo-700 shadow-lg transition hover:bg-indigo-50"
            >
              <MessageCircle className="h-5 w-5" /> Ask the assistant
            </button>
          </div>
        </div>
      </div>

      <div className="relative z-10 mx-auto -mt-10 max-w-7xl px-4 pb-16 sm:px-6 lg:px-8">
        {/* Notice (clause 1.4) */}
        <div className="mb-6 flex gap-3 rounded-xl border border-indigo-100 bg-white p-4 shadow-xl">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-100">
            <ShieldCheck className="h-5 w-5 text-indigo-700" />
          </div>
          <p className="text-sm text-gray-600">
            <span className="font-semibold text-gray-900">This page is the official source of our rules.</span> The JetSetGo
            assistant answers only from this policy and shows the clause behind every answer. If information anywhere else
            appears to conflict with it, please contact Customer Care before you travel or buy, so we can confirm the correct
            rule (clause 1.4).
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-[260px_1fr]">
          {/* Table of contents */}
          <aside className="hidden lg:block">
            <nav className="sticky top-6 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
              <div className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-400">Contents</div>
              <ul className="space-y-0.5">
                {sections.map((s) => (
                  <li key={s.num}>
                    <a
                      href={`#section-${s.num}`}
                      className="group flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-600 transition hover:bg-indigo-50 hover:text-indigo-700"
                    >
                      <span className="w-5 font-mono text-xs text-indigo-400">{s.num}</span>
                      <span className="flex-1">{s.title}</span>
                      <ChevronRight className="h-3.5 w-3.5 opacity-0 transition group-hover:opacity-100" />
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </aside>

          {/* Sections */}
          <main className="space-y-5">
            {q && (
              <div className="text-sm text-gray-500">
                {matchCount} clause{matchCount === 1 ? "" : "s"} matching “{q}”
              </div>
            )}
            {visible.length === 0 && (
              <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
                <Info className="mx-auto mb-2 h-8 w-8 text-gray-300" />
                <p className="text-gray-600">Nothing in the policy matches “{q}”.</p>
                <button
                  type="button"
                  onClick={() => openPolicyChat(q)}
                  className="mt-3 text-sm font-semibold text-indigo-600 hover:underline"
                >
                  Ask the assistant instead →
                </button>
              </div>
            )}
            {visible.map((s) => {
              const id = `section-${s.num}`;
              return (
                <section
                  key={s.num}
                  id={id}
                  className={`scroll-mt-6 rounded-xl border bg-white p-6 shadow-sm transition-all duration-500 ${
                    activeId === id ? "border-indigo-400 shadow-lg ring-4 ring-indigo-100" : "border-gray-100"
                  }`}
                >
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <h2 className="flex items-center gap-3 text-xl font-bold text-indigo-900">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-blue-500 font-mono text-sm text-white shadow">
                        {s.num}
                      </span>
                      <Highlight text={s.title} query={q} />
                    </h2>
                    <button
                      type="button"
                      onClick={() => openPolicyChat(SECTION_QUESTIONS[s.num] || `What does the policy say about ${s.title.toLowerCase()}?`)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-indigo-100 px-3 py-1 text-xs font-medium text-indigo-600 transition hover:border-indigo-300 hover:bg-indigo-50"
                    >
                      <MessageCircle className="h-3.5 w-3.5" /> Ask about this
                    </button>
                  </div>
                  <div className="space-y-3">
                    {s.clauses.map((c, i) => (
                      <div key={c.num || i} id={c.num ? `clause-${c.num.replace(".", "-")}` : undefined} className="flex gap-3">
                        {c.num && (
                          <span className="mt-0.5 h-fit shrink-0 rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-xs font-semibold text-indigo-600">
                            {c.num}
                          </span>
                        )}
                        <p className="leading-relaxed text-gray-700">
                          <Highlight text={c.text} query={q} />
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </main>
        </div>
      </div>

      <Footer />
    </div>
  );
}
