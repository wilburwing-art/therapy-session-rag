"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type ConsentRecord = {
  id: string;
  patient_id: string;
  therapist_id: string;
  consent_type: "recording" | "transcription" | "ai_analysis";
  status: "granted" | "revoked";
  granted_at: string;
  revoked_at: string | null;
};

const REQUIRED_TYPES = ["recording", "transcription", "ai_analysis"] as const;

export function ConsentPanel({
  patientId,
  therapistId,
  activeConsents,
}: {
  patientId: string;
  therapistId: string;
  activeConsents: ConsentRecord[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const [attested, setAttested] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeTypes = new Set(
    activeConsents
      .filter((c) => c.status === "granted" && c.revoked_at === null)
      .map((c) => c.consent_type),
  );
  const allGranted = REQUIRED_TYPES.every((t) => activeTypes.has(t));

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/v1/consent/bulk", {
        json: {
          patient_id: patientId,
          therapist_id: therapistId,
          attested: true,
          notes: notes || null,
        },
      });
      setOpen(false);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't record consent");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className={`rounded-xl border p-4 ${allGranted ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}
    >
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center sm:gap-4">
        <div>
          <p
            className={`text-sm font-semibold ${allGranted ? "text-emerald-900" : "text-amber-900"}`}
          >
            {allGranted
              ? "Consent on file: recording, transcription, AI analysis"
              : "Consent needed before recording sessions"}
          </p>
          {!allGranted && (
            <p className="mt-1 text-sm text-amber-900">
              Missing:{" "}
              {REQUIRED_TYPES.filter((t) => !activeTypes.has(t)).join(", ")}
            </p>
          )}
        </div>
        {!allGranted && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="w-full shrink-0 rounded-md bg-amber-900 px-3 py-3 text-sm text-white hover:bg-amber-950 sm:w-auto sm:py-1.5"
          >
            Record consent
          </button>
        )}
      </div>

      {open && (
        <div className="mt-4 space-y-3 rounded-md border border-amber-200 bg-white p-4">
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={attested}
              onChange={(e) => setAttested(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              I attest that the patient has given informed consent (signed or
              explicit verbal) for recording their sessions, transcription, and
              AI-based analysis for their own treatment.
            </span>
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Optional notes (e.g. 'signed consent form in file')"
            className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex flex-col justify-end gap-2 sm:flex-row">
            <button
              onClick={() => setOpen(false)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-3 text-sm hover:bg-slate-50 sm:w-auto sm:py-1.5"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting || !attested}
              className="w-full rounded-md bg-emerald-700 px-3 py-3 text-sm text-white hover:bg-emerald-800 disabled:opacity-50 sm:w-auto sm:py-1.5"
            >
              {submitting ? "Saving…" : "Save consent"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
