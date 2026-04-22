"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type SaveStatus =
  | { kind: "idle" }
  | { kind: "dirty" }
  | { kind: "saving" }
  | { kind: "saved"; at: number }
  | { kind: "error"; message: string };

const DEBOUNCE_MS = 1500;
const MAX_LENGTH = 20000;

export function NotesEditor({
  sessionId,
  initialNotes,
}: {
  sessionId: string;
  initialNotes: string;
}) {
  const [value, setValue] = useState(initialNotes);
  const [status, setStatus] = useState<SaveStatus>({ kind: "idle" });
  const lastSavedRef = useRef<string>(initialNotes);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useCallback(
    async (next: string) => {
      if (next === lastSavedRef.current) {
        setStatus({ kind: "saved", at: Date.now() });
        return;
      }
      setStatus({ kind: "saving" });
      try {
        await apiFetch(`/v1/sessions/${sessionId}/notes`, {
          method: "PATCH",
          json: { notes: next.length === 0 ? null : next },
        });
        lastSavedRef.current = next;
        setStatus({ kind: "saved", at: Date.now() });
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Failed to save notes";
        setStatus({ kind: "error", message });
      }
    },
    [sessionId],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = event.target.value;
    setValue(next);
    setStatus({ kind: "dirty" });
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      void save(next);
    }, DEBOUNCE_MS);
  }

  async function handleBlur() {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (value !== lastSavedRef.current) {
      await save(value);
    }
  }

  const statusLine = renderStatus(status);
  const tooLong = value.length > MAX_LENGTH;

  return (
    <section className="prose-surface">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Therapist notes</h2>
        <span
          className="text-xs text-slate-500"
          aria-live="polite"
          role="status"
        >
          {statusLine}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Private to you. Not shown to patients.
      </p>
      <textarea
        value={value}
        onChange={handleChange}
        onBlur={handleBlur}
        maxLength={MAX_LENGTH}
        rows={6}
        placeholder="Capture private notes about this session…"
        className="mt-3 w-full rounded-md border border-slate-300 p-3 font-sans text-sm text-slate-800 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      />
      <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
        <span>{value.length} / {MAX_LENGTH}</span>
        {tooLong && (
          <span className="text-red-600">
            Notes exceed the {MAX_LENGTH.toLocaleString()} character limit
          </span>
        )}
      </div>
    </section>
  );
}

function renderStatus(status: SaveStatus): string {
  switch (status.kind) {
    case "idle":
      return "";
    case "dirty":
      return "Unsaved changes…";
    case "saving":
      return "Saving…";
    case "saved":
      return "Saved just now";
    case "error":
      return `Error: ${status.message}`;
  }
}
