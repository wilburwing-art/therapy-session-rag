"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { currentPatient } from "@/lib/auth";
import type { CurrentPatient, HomeworkItemRecord } from "@/lib/types";

// Dedicated homework page. The chat surface shows only the next few
// open items; this page is the full list with filters so the patient
// can review previously completed work too.

type Filter = "open" | "completed" | "all";

export default function PatientHomeworkPage() {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "needs_link" }
    | { kind: "ready"; patient: CurrentPatient }
  >({ kind: "loading" });
  const [filter, setFilter] = useState<Filter>("open");
  const [items, setItems] = useState<HomeworkItemRecord[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const me = await currentPatient();
      if (cancelled) return;
      setState(me ? { kind: "ready", patient: me } : { kind: "needs_link" });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async (f: Filter) => {
    setItems(null);
    setError(null);
    try {
      const query =
        f === "all"
          ? "/v1/homework/me?limit=100"
          : `/v1/homework/me?completed=${f === "completed"}&limit=100`;
      const rows = await apiFetch<HomeworkItemRecord[]>(query);
      setItems(rows);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't load homework.",
      );
      setItems([]);
    }
  }, []);

  useEffect(() => {
    if (state.kind !== "ready") return;
    void load(filter);
  }, [state.kind, filter, load]);

  async function toggle(item: HomeworkItemRecord) {
    if (busyId) return;
    setBusyId(item.id);
    try {
      const updated = await apiFetch<HomeworkItemRecord>(
        `/v1/homework/${item.id}`,
        {
          method: "PATCH",
          json: { completed: !item.completed },
        },
      );
      setItems((prev) =>
        prev
          ? prev.map((h) => (h.id === updated.id ? updated : h))
          : prev,
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not update homework.",
      );
    } finally {
      setBusyId(null);
    }
  }

  if (state.kind === "loading") {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-slate-600">Loading your homework…</p>
      </main>
    );
  }
  if (state.kind === "needs_link") {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">You&apos;ll need a new link</h1>
          <p className="mt-2 text-slate-600">
            Open the magic link your therapist sent you to see your homework.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Homework</h1>
        <p className="mt-1 text-sm text-slate-600">
          Between-session tasks you and your therapist agreed on. Checking an
          item off updates what your therapist sees.
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Homework filter"
        className="mb-4 flex gap-2 text-sm"
      >
        {(["open", "completed", "all"] as Filter[]).map((f) => (
          <button
            key={f}
            role="tab"
            aria-selected={filter === f}
            onClick={() => setFilter(f)}
            className={
              filter === f
                ? "rounded-full bg-brand-600 px-3 py-1 text-white"
                : "rounded-full border border-slate-300 px-3 py-1 text-slate-700 hover:bg-slate-100"
            }
          >
            {f === "open"
              ? "Open"
              : f === "completed"
                ? "Completed"
                : "All"}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="mb-4 text-sm text-red-600">
          {error}
        </p>
      )}

      {items === null ? (
        <p className="text-slate-600">Loading…</p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
          {filter === "open"
            ? "Nothing open right now. Check back after your next session."
            : filter === "completed"
              ? "No completed homework yet."
              : "No homework yet."}
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm"
            >
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                checked={item.completed}
                disabled={busyId === item.id}
                onChange={() => void toggle(item)}
                aria-label={`Mark "${item.task}" ${item.completed ? "incomplete" : "complete"}`}
              />
              <div className="flex-1">
                <p
                  className={
                    item.completed
                      ? "text-sm text-slate-500 line-through"
                      : "text-sm text-slate-800"
                  }
                >
                  {item.task}
                </p>
                {item.notes && (
                  <p className="mt-0.5 text-xs text-slate-500">{item.notes}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
