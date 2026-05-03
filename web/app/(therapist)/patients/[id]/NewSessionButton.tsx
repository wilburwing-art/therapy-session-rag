"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type ActiveConsentRecord = {
  id: string;
  consent_type: "recording" | "transcription" | "ai_analysis";
  status: "granted" | "revoked";
};

type SessionRead = {
  id: string;
};

export function NewSessionButton({
  patientId,
  therapistId,
  activeConsents,
}: {
  patientId: string;
  therapistId: string;
  activeConsents: ActiveConsentRecord[];
}) {
  const router = useRouter();
  const recordingConsent = activeConsents.find(
    (c) => c.consent_type === "recording" && c.status === "granted",
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createSession() {
    if (!recordingConsent) {
      setError("Record patient consent before creating a session.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<SessionRead>("/v1/sessions", {
        json: {
          patient_id: patientId,
          therapist_id: therapistId,
          consent_id: recordingConsent.id,
          session_date: new Date().toISOString(),
          session_type: "upload",
        },
      });
      router.push(`/sessions/${res.id}/record`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start session");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={createSession}
        disabled={loading || !recordingConsent}
        className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
        title={
          recordingConsent ? undefined : "Requires active recording consent"
        }
      >
        {loading ? "Starting…" : "+ New session"}
      </button>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
