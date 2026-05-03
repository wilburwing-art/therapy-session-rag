"use client";

import { useState } from "react";

export function DownloadRecordButton({ patientId }: { patientId: string }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/patients/${patientId}/record.pdf`, {
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error(
          res.status === 404
            ? "Patient record is not available."
            : `Download failed (HTTP ${res.status}).`,
        );
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = /filename="?([^"]+)"?/i.exec(disposition);
      const filename = match ? match[1] : `patient-${patientId}-record.pdf`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={handleDownload}
        disabled={downloading}
        className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-800 hover:bg-slate-100 disabled:opacity-50"
      >
        {downloading ? "Preparing…" : "Download record (PDF)"}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
