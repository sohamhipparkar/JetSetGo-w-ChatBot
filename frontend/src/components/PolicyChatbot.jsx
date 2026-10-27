import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Ban,
  BookOpen,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  Info,
  MessageCircle,
  Plane,
  Quote,
  RotateCcw,
  ScrollText,
  Send,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import MiniMarkdown from "../lib/miniMarkdown";
import { askPolicyBot, OPEN_CHAT_EVENT } from "../lib/policyApi";

/*
 * JetSetGo policy chatbot.
 * The same verified pipeline as the Flight Policy Assistant: every answer is grounded in the
 * JetSetGo Travel Policy, quotes are checked word-for-word, a second Gemini pass audits it,
 * and anything unverifiable falls back to the policy's exact text.
 */

const STORAGE_KEY = "jetsetgo-policy-chat-v1";

const SAMPLE_QUESTIONS = [
  "My grandmother passed away. Can I get a bereavement fare refund after I travel?",
  "Can I cancel a Basic fare and get my money back?",
  "How much does an extra checked bag cost?",
  "My flight was delayed 6 hours. What am I entitled to?",
  "Can my 8-year-old fly alone?",
  "Do you allow pets in the cargo hold?",
];

const LOADING_STEPS = ["Reading the Travel Policy…", "Checking every quote…", "Verifying the answer…"];

const STATUS_STYLE = {
  verified: { cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", Icon: CircleCheck, label: "Verified against policy" },
  verified_with_caveats: { cls: "bg-amber-50 text-amber-700 ring-amber-200", Icon: TriangleAlert, label: "Verified – check the conditions" },
  not_in_policy: { cls: "bg-sky-50 text-sky-700 ring-sky-200", Icon: Info, label: "Not covered by the policy" },
  safe_mode: { cls: "bg-violet-50 text-violet-700 ring-violet-200", Icon: ShieldCheck, label: "Showing exact policy text" },
  blocked: { cls: "bg-rose-50 text-rose-700 ring-rose-200", Icon: Ban, label: "Request not allowed" },
  error: { cls: "bg-rose-50 text-rose-700 ring-rose-200", Icon: TriangleAlert, label: "Service error" },
};

function loadMessages() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

function saveMessages(messages) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-40)));
  } catch {
    /* storage unavailable - chat still works for this page */
  }
}

/* ------------------------------------------------------------------ pieces */

function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.not_in_policy;
  const { Icon } = s;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ${s.cls}`}>
      <Icon className="h-3.5 w-3.5" />
      {s.label}
    </span>
  );
}

function Citation({ cit, onNavigate }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex overflow-hidden rounded-xl border border-indigo-100 bg-white">
      <div className="flex w-14 shrink-0 flex-col items-center justify-center border-r-2 border-dashed border-indigo-200 bg-indigo-50 px-1 py-2">
        <span className="text-[9px] font-semibold tracking-widest text-indigo-400">CLAUSE</span>
        <span className="font-mono text-xs font-bold text-indigo-700">{cit.chunk_id}</span>
      </div>
      <div className="min-w-0 flex-1 p-2.5">
        {cit.anchor ? (
          <Link
            to={`/travel-policy#${cit.anchor}`}
            onClick={onNavigate}
            className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
          >
            {cit.label} ↗
          </Link>
        ) : (
          <span className="text-[11px] font-semibold text-indigo-600">{cit.label}</span>
        )}
        {cit.quote && (
          <div className="mt-1.5 flex gap-1.5 rounded-md border-l-2 border-indigo-500 bg-indigo-50/70 px-2 py-1.5 text-xs italic text-gray-800">
            <Quote className="mt-0.5 h-3 w-3 shrink-0 text-indigo-400" />
            <span>{cit.quote}</span>
          </div>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-medium text-gray-500 hover:text-indigo-600"
        >
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {open ? "Hide full clause" : "Show full clause"}
        </button>
        {open && <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-gray-600">{cit.clause_text}</p>}
      </div>
    </div>
  );
}

function BotReply({ reply, onNavigate }) {
  const [showSources, setShowSources] = useState(reply.status === "safe_mode");
  const [showCheck, setShowCheck] = useState(false);
  const ver = reply.verification || {};
  const nCites = reply.citations?.length || 0;
  const verified = reply.status === "verified" || reply.status === "verified_with_caveats";

  return (
    <div className="space-y-2.5">
      <StatusBadge status={reply.status} />
      <MiniMarkdown text={reply.answer} className="text-sm leading-relaxed text-gray-700" />

      {reply.conditions?.length > 0 && (
        <div className="rounded-lg border-l-4 border-amber-400 bg-amber-50 px-3 py-2">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-amber-700">Conditions & exceptions</div>
          <ul className="list-disc space-y-0.5 pl-4 text-xs text-gray-700">
            {reply.conditions.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {reply.follow_up_question && <p className="text-sm italic text-indigo-700">💬 {reply.follow_up_question}</p>}

      {reply.notes?.map((note, i) => (
        <p key={i} className="flex gap-1.5 text-[11px] leading-snug text-gray-500">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          {note}
        </p>
      ))}

      {nCites > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowSources((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-700 hover:text-indigo-900"
          >
            <ScrollText className="h-3.5 w-3.5" />
            {verified
              ? `${nCites} policy clause${nCites > 1 ? "s" : ""} used`
              : reply.status === "not_in_policy"
                ? "Related clauses"
                : "Exact policy text"}
            {showSources ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {showSources && (
            <div className="mt-2 space-y-2">
              {reply.citations.map((cit, i) => (
                <Citation key={`${cit.chunk_id}-${i}`} cit={cit} onNavigate={onNavigate} />
              ))}
            </div>
          )}
        </div>
      )}

      {ver.verdict && (
        <div>
          <button
            type="button"
            onClick={() => setShowCheck((v) => !v)}
            className="inline-flex items-center gap-1 text-[11px] font-medium text-gray-400 hover:text-gray-600"
          >
            <ShieldCheck className="h-3 w-3" /> Verification details
            {showCheck ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          {showCheck && (
            <div className="mt-1.5 space-y-1 rounded-lg bg-gray-50 p-2 text-[11px] text-gray-600">
              <div className="flex flex-wrap gap-1.5">
                <span className="rounded-full bg-indigo-100 px-2 py-0.5 font-mono text-indigo-700">verdict: {ver.verdict}</span>
                <span className="rounded-full bg-amber-100 px-2 py-0.5 font-mono text-amber-700">confidence: {reply.confidence}</span>
              </div>
              {ver.explanation && <p>{ver.explanation}</p>}
              {ver.problem_claims?.map((c, i) => (
                <p key={i}>• {c}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TypingIndicator() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % LOADING_STEPS.length), 2200);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex items-center gap-3">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-2 w-2 animate-bounce rounded-full bg-indigo-400"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
      <span className="text-xs text-gray-500">{LOADING_STEPS[step]}</span>
    </div>
  );
}

function BotAvatar() {
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-600 to-blue-500 shadow-md">
      <Plane className="h-4 w-4 -rotate-45 text-white" />
    </div>
  );
}

/* ------------------------------------------------------------------ widget */

export default function PolicyChatbot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(loadMessages);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showTeaser, setShowTeaser] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => saveMessages(messages), [messages]);

  useEffect(() => {
    const t = setTimeout(() => setShowTeaser(true), 1500);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading, open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const send = useCallback(
    async (text, base) => {
      const question = (text ?? input).trim();
      if (!question || loading) return;
      const prior = base ?? messages;
      const history = prior
        .filter((m) => m.role === "user" || (m.role === "assistant" && m.reply))
        .map((m) => ({ role: m.role, content: m.role === "user" ? m.content : m.reply.answer }));

      setMessages([...prior, { role: "user", content: question }]);
      setInput("");
      setLoading(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const reply = await askPolicyBot(question, history, { signal: controller.signal });
        setMessages((prev) => [...prev, { role: "assistant", reply }]);
      } catch (err) {
        if (err.name !== "AbortError") {
          setMessages((prev) => [...prev, { role: "error", content: err.message, question }]);
        }
      } finally {
        setLoading(false);
        abortRef.current = null;
      }
    },
    [input, loading, messages]
  );

  // Other pages (Travel Policy) can open the chat, optionally with a question.
  useEffect(() => {
    const handler = (e) => {
      setOpen(true);
      const q = e.detail?.question;
      if (q) setTimeout(() => send(q), 50);
    };
    window.addEventListener(OPEN_CHAT_EVENT, handler);
    return () => window.removeEventListener(OPEN_CHAT_EVENT, handler);
  }, [send]);

  const clearChat = () => {
    abortRef.current?.abort();
    setMessages([]);
    setLoading(false);
  };

  // Drop the failed question + error message, then ask again.
  const retry = (question) => send(question, messages.slice(0, -2));

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <>
      {/* Launcher */}
      {!open && (
        <div className="fixed bottom-5 right-5 z-[60] flex items-end gap-3">
          {showTeaser && messages.length === 0 && (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="mb-2 hidden max-w-[220px] rounded-2xl rounded-br-sm bg-white px-4 py-2.5 text-left text-sm text-gray-700 shadow-xl ring-1 ring-indigo-100 transition hover:ring-indigo-300 sm:block"
            >
              <span className="font-semibold text-indigo-700">Questions about your trip?</span>
              <br />
              Ask about refunds, baggage & bookings.
            </button>
          )}
          <button
            type="button"
            aria-label="Open JetSetGo policy assistant"
            onClick={() => setOpen(true)}
            className="group relative flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-indigo-700 via-blue-700 to-blue-500 text-white shadow-2xl ring-4 ring-white transition hover:scale-105"
          >
            <span className="absolute inset-0 animate-ping rounded-full bg-blue-500 opacity-20" />
            <MessageCircle className="h-6 w-6 transition group-hover:scale-110" />
          </button>
        </div>
      )}

      {/* Panel */}
      {open && (
        <div
          role="dialog"
          aria-label="JetSetGo policy assistant"
          className="fixed inset-0 z-[60] flex flex-col overflow-hidden bg-white shadow-2xl sm:inset-auto sm:bottom-5 sm:right-5 sm:h-[640px] sm:max-h-[calc(100vh-2.5rem)] sm:w-[400px] sm:rounded-2xl sm:ring-1 sm:ring-indigo-100"
        >
          {/* Header */}
          <div className="relative bg-gradient-to-r from-indigo-900 via-blue-800 to-blue-700 px-4 py-3.5 text-white">
            <Plane className="pointer-events-none absolute -right-2 -top-2 h-20 w-20 rotate-12 text-white opacity-10" />
            <div className="relative flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-lg">
                <Plane className="h-5 w-5 -rotate-45 text-blue-700" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-bold tracking-wide">JetSetGo Assistant</div>
                <div className="flex items-center gap-1.5 text-[11px] text-blue-100">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  Answers verified against our Travel Policy
                </div>
              </div>
              <button
                type="button"
                onClick={clearChat}
                title="New conversation"
                className="rounded-full p-2 text-blue-100 transition hover:bg-white/10 hover:text-white"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                title="Close"
                className="rounded-full p-2 text-blue-100 transition hover:bg-white/10 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto bg-gradient-to-b from-indigo-50/60 to-white px-4 py-4">
            {messages.length === 0 && (
              <div className="space-y-4">
                <div className="flex gap-2.5">
                  <BotAvatar />
                  <div className="rounded-2xl rounded-tl-sm bg-white px-4 py-3 text-sm text-gray-700 shadow-sm ring-1 ring-indigo-100">
                    <p className="font-semibold text-gray-900">Hi! 👋 I'm the JetSetGo policy assistant.</p>
                    <p className="mt-1">
                      Ask me about fares, refunds, changes, baggage or travel rules. Every answer comes straight from our{" "}
                      <Link to="/travel-policy" onClick={() => setOpen(false)} className="font-medium text-indigo-600 hover:underline">
                        Travel Policy
                      </Link>
                      , with the exact clause shown.
                    </p>
                  </div>
                </div>
                <div>
                  <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400">Try asking</div>
                  <div className="flex flex-col gap-2">
                    {SAMPLE_QUESTIONS.map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => send(q)}
                        className="rounded-xl border border-indigo-100 bg-white px-3 py-2 text-left text-xs text-gray-700 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-800"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {messages.map((m, i) => {
              if (m.role === "user") {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-gradient-to-br from-indigo-600 to-blue-600 px-4 py-2.5 text-sm text-white shadow-md">
                      {m.content}
                    </div>
                  </div>
                );
              }
              if (m.role === "error") {
                return (
                  <div key={i} className="flex gap-2.5">
                    <BotAvatar />
                    <div className="rounded-2xl rounded-tl-sm bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-200">
                      <p>{m.content}</p>
                      {i === messages.length - 1 && (
                        <button
                          type="button"
                          onClick={() => retry(m.question)}
                          className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-rose-700 hover:underline"
                        >
                          <RotateCcw className="h-3 w-3" /> Try again
                        </button>
                      )}
                    </div>
                  </div>
                );
              }
              return (
                <div key={i} className="flex gap-2.5">
                  <BotAvatar />
                  <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-indigo-100">
                    <BotReply reply={m.reply} onNavigate={() => setOpen(window.innerWidth >= 640)} />
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="flex gap-2.5">
                <BotAvatar />
                <div className="rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-indigo-100">
                  <TypingIndicator />
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-gray-100 bg-white px-3 pb-3 pt-2.5">
            <div className="flex items-end gap-2 rounded-2xl border border-gray-200 bg-gray-50 px-3 py-2 transition focus-within:border-indigo-400 focus-within:bg-white focus-within:ring-4 focus-within:ring-indigo-100">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                maxLength={1000}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Ask about refunds, baggage, changes…"
                className="max-h-28 flex-1 resize-none bg-transparent text-sm text-gray-800 placeholder-gray-400 outline-none"
                style={{ fieldSizing: "content" }}
              />
              <button
                type="button"
                onClick={() => send()}
                disabled={!input.trim() || loading}
                aria-label="Send"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-blue-600 text-white shadow-md transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-1.5 flex items-center justify-between px-1 text-[10px] text-gray-400">
              <span className="flex items-center gap-1">
                <BookOpen className="h-3 w-3" /> Policy info only · can't change bookings
              </span>
              {input.length > 900 && <span>{input.length}/1000</span>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
