"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { ChatResponse, ChatSource, CurrentPatient } from "@/lib/types";

type UIMessage =
  | { role: "user"; content: string; id: string }
  | {
      role: "assistant";
      content: string;
      id: string;
      sources: ChatSource[];
    };

export function ChatSurface({ patient }: { patient: CurrentPatient }) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const userMsg: UIMessage = {
      role: "user",
      content: trimmed,
      id: crypto.randomUUID(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const res = await apiFetch<ChatResponse>("/v1/chat/patient", {
        json: {
          message: trimmed,
          conversation_id: conversationId,
          top_k: 5,
        },
      });
      setConversationId(res.conversation_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.response,
          id: crypto.randomUUID(),
          sources: res.sources,
        },
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex min-h-[70vh] flex-col">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">
          Hi{patient.full_name ? `, ${patient.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Ask anything about your recent sessions. Answers come with citations
          back to the session and timestamp.
        </p>
      </header>

      <div className="flex-1 space-y-4 pb-40">
        {messages.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
            Try: <em>&ldquo;What did we discuss about sleep last time?&rdquo;</em>
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <div
              key={m.id}
              className="ml-auto max-w-[85%] rounded-2xl bg-brand-600 px-4 py-2 text-white shadow sm:max-w-[80%]"
            >
              {m.content}
            </div>
          ) : (
            <div
              key={m.id}
              className="max-w-[90%] rounded-2xl bg-white px-4 py-3 shadow sm:max-w-[85%]"
            >
              <p className="whitespace-pre-wrap text-slate-800">{m.content}</p>
              {m.sources.length > 0 && (
                <details className="mt-3 text-xs text-slate-500">
                  <summary className="cursor-pointer font-medium text-slate-600">
                    {m.sources.length} source{m.sources.length === 1 ? "" : "s"}
                  </summary>
                  <ul className="mt-2 space-y-2">
                    {m.sources.map((s) => (
                      <li key={s.chunk_id} className="rounded-md bg-slate-50 p-2">
                        <p className="text-slate-600">
                          {s.start_time != null && (
                            <span className="font-medium text-brand-700">
                              @{Math.round(s.start_time)}s ·{" "}
                            </span>
                          )}
                          {s.content_preview.slice(0, 160)}…
                        </p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ),
        )}
        {sending && (
          <div className="max-w-[80%] rounded-2xl bg-white px-4 py-3 text-slate-500 shadow">
            <span className="inline-block animate-pulse">Thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error}
        </p>
      )}

      <form
        onSubmit={send}
        className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white px-4 pt-3 sm:px-6"
        style={{
          paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 0.75rem)",
        }}
      >
        <div className="mx-auto flex max-w-2xl gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(e as unknown as React.FormEvent);
              }
            }}
            rows={2}
            placeholder="Ask your session history…"
            disabled={sending}
            className="w-full flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2 shadow-sm focus:border-brand-500 focus:ring-brand-500"
          />
          <button
            type="submit"
            disabled={sending || input.trim().length === 0}
            className="self-end rounded-xl bg-brand-600 px-4 py-3 text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
