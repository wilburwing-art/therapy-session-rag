"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export function MagicLinkButton({ patientId }: { patientId: string }) {
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function issue() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ token: string; expires_at: string }>(
        "/v1/auth/patient/magic-link",
        { json: { patient_id: patientId } },
      );
      const origin =
        typeof window !== "undefined" ? window.location.origin : "";
      setLink(`${origin}/chat?t=${encodeURIComponent(res.token)}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to issue link");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="text-right">
      <button
        onClick={issue}
        disabled={loading}
        className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
      >
        {loading ? "Issuing…" : "Send chatbot link"}
      </button>
      {link && (
        <div className="mt-3 max-w-md rounded-md bg-slate-100 p-3 text-xs text-slate-700">
          <p className="mb-1 font-medium">Copy this link for the patient:</p>
          <code className="break-all">{link}</code>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
