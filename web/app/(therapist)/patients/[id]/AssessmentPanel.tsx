"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import {
  type Assessment,
  type AssessmentInstrument,
  GAD7_QUESTIONS,
  LIKERT_OPTIONS,
  PHQ9_QUESTIONS,
  severityColor,
} from "@/lib/assessment";

function Sparkline({ scores, max }: { scores: number[]; max: number }) {
  if (scores.length === 0) return null;
  const width = 160;
  const height = 32;
  const stepX = scores.length > 1 ? width / (scores.length - 1) : 0;
  const points = scores
    .map(
      (s, i) => `${i * stepX},${height - (s / max) * height}`,
    )
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-8 w-40"
      preserveAspectRatio="none"
    >
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  );
}

export function AssessmentPanel({
  patientId,
  assessments,
}: {
  patientId: string;
  assessments: Assessment[];
}) {
  const [open, setOpen] = useState<AssessmentInstrument | null>(null);
  const router = useRouter();

  const latest = (instr: AssessmentInstrument) =>
    assessments.find((a) => a.instrument === instr) ?? null;
  const phq = latest("phq9");
  const gad = latest("gad7");

  return (
    <div>
      <div className="grid gap-4 md:grid-cols-2">
        <Card
          title="PHQ-9"
          latest={phq}
          max={27}
          onStart={() => setOpen("phq9")}
          history={assessments.filter((a) => a.instrument === "phq9")}
        />
        <Card
          title="GAD-7"
          latest={gad}
          max={21}
          onStart={() => setOpen("gad7")}
          history={assessments.filter((a) => a.instrument === "gad7")}
        />
      </div>

      {open && (
        <AssessmentForm
          instrument={open}
          patientId={patientId}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null);
            router.refresh();
          }}
        />
      )}
    </div>
  );
}

function Card({
  title,
  latest,
  max,
  onStart,
  history,
}: {
  title: string;
  latest: Assessment | null;
  max: number;
  onStart: () => void;
  history: Assessment[];
}) {
  const chronological = [...history]
    .sort(
      (a, b) =>
        new Date(a.administered_at).getTime() -
        new Date(b.administered_at).getTime(),
    )
    .map((a) => a.total_score);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          {title}
        </h3>
        <button
          onClick={onStart}
          className="rounded-md border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
        >
          Record new
        </button>
      </div>
      {latest ? (
        <div className="mt-3">
          <p className="text-3xl font-semibold text-slate-900">
            {latest.total_score}
            <span className="ml-2 text-base font-normal text-slate-500">
              / {max}
            </span>
          </p>
          <div className="mt-1 flex items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${severityColor(latest.severity)}`}
            >
              {(latest.severity ?? "unknown").replace("_", " ")}
            </span>
            <span className="text-xs text-slate-500">
              {new Date(latest.administered_at).toLocaleDateString()}
            </span>
          </div>
          {chronological.length > 1 && (
            <div className="mt-3 flex items-center gap-3 text-brand-700">
              <Sparkline scores={chronological} max={max} />
              <span className="text-xs text-slate-500">
                last {chronological.length}
              </span>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No scores recorded yet.</p>
      )}
    </div>
  );
}

function AssessmentForm({
  instrument,
  patientId,
  onClose,
  onSaved,
}: {
  instrument: AssessmentInstrument;
  patientId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const questions = instrument === "phq9" ? PHQ9_QUESTIONS : GAD7_QUESTIONS;
  const [responses, setResponses] = useState<number[]>(
    new Array(questions.length).fill(-1),
  );
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const complete = responses.every((r) => r >= 0);

  async function submit() {
    if (!complete) {
      setError("Answer every question before saving.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch(`/v1/patients/${patientId}/assessments`, {
        json: {
          instrument,
          responses,
          notes: notes || null,
        },
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {instrument.toUpperCase()} — over the past 2 weeks
          </h2>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-900"
          >
            ✕
          </button>
        </div>
        <ol className="space-y-4">
          {questions.map((q, i) => (
            <li key={i} className="space-y-1">
              <p className="text-sm">
                <span className="text-slate-500">{i + 1}.</span> {q}
              </p>
              <div className="flex gap-3 text-xs">
                {LIKERT_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className={`flex flex-1 cursor-pointer flex-col items-center gap-1 rounded-md border px-2 py-1.5 ${responses[i] === opt.value ? "border-brand-600 bg-brand-50" : "border-slate-200"}`}
                  >
                    <input
                      type="radio"
                      name={`q${i}`}
                      className="sr-only"
                      checked={responses[i] === opt.value}
                      onChange={() =>
                        setResponses((rs) => {
                          const next = [...rs];
                          next[i] = opt.value;
                          return next;
                        })
                      }
                    />
                    <span className="font-semibold">{opt.value}</span>
                    <span className="text-center text-slate-600">
                      {opt.label}
                    </span>
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ol>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Optional notes"
          className="mt-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        {error && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            {error}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={submitting || !complete}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
