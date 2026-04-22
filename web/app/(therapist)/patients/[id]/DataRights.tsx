"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export function DataRights({
  patientId,
  patientEmail,
}: {
  patientId: string;
  patientEmail: string;
}) {
  const router = useRouter();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      const bundle = await apiFetch<Record<string, unknown>>(
        `/v1/patients/${patientId}/export`,
      );
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `patient-${patientId}-export.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(
        err instanceof ApiError ? err.message : "Export failed",
      );
    } finally {
      setExporting(false);
    }
  }

  return (
    <section className="rounded-xl border border-red-200 bg-red-50 p-5">
      <h2 className="text-lg font-semibold text-red-900">Data rights</h2>
      <p className="mt-1 text-sm text-red-800">
        HIPAA right-to-access and right-to-deletion actions. The deletion is
        irreversible; all sessions, transcripts, conversations, and
        assessments are removed.
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          onClick={handleExport}
          disabled={exporting}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 hover:bg-slate-100 disabled:opacity-50"
        >
          {exporting ? "Exporting…" : "Export patient data (JSON)"}
        </button>
        <button
          onClick={() => setShowDelete(true)}
          className="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
        >
          Delete patient and all data
        </button>
      </div>
      {exportError && (
        <p className="mt-3 text-sm text-red-700">{exportError}</p>
      )}
      {showDelete && (
        <DeleteModal
          patientId={patientId}
          patientEmail={patientEmail}
          onClose={() => setShowDelete(false)}
          onDeleted={() => {
            setShowDelete(false);
            router.push("/dashboard");
          }}
        />
      )}
    </section>
  );
}

function DeleteModal({
  patientId,
  patientEmail,
  onClose,
  onDeleted,
}: {
  patientId: string;
  patientEmail: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setPending(true);
    setError(null);
    try {
      await apiFetch(`/v1/patients/${patientId}`, {
        method: "DELETE",
        json: { confirm_email: confirmation },
      });
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    } finally {
      setPending(false);
    }
  }

  const emailMatches =
    confirmation.trim().toLowerCase() === patientEmail.trim().toLowerCase();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h3 className="text-xl font-semibold text-slate-900">
          Delete patient?
        </h3>
        <p className="mt-2 text-sm text-slate-700">
          This permanently removes the patient record and every session,
          transcript, recap, theme document, conversation, and assessment
          tied to them. This cannot be undone.
        </p>
        <p className="mt-3 text-sm text-slate-700">
          To confirm, type the patient&apos;s email address below:
        </p>
        <p className="mt-1 font-mono text-xs text-slate-500">{patientEmail}</p>
        <input
          type="email"
          autoComplete="off"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          placeholder="patient@example.com"
        />
        {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={!emailMatches || pending}
            className="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
          >
            {pending ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
