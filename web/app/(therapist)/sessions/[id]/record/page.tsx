"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { AudioRecorder } from "@/components/AudioRecorder";
import { apiFetch, ApiError } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";

export default function RecordSessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: sessionId } = use(params);
  const router = useRouter();

  const [session, setSession] = useState<SessionSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<SessionSummary>(`/v1/sessions/${sessionId}`)
      .then((s) => !cancelled && setSession(s))
      .catch((err) =>
        setLoadError(
          err instanceof ApiError ? err.message : "Couldn't load session",
        ),
      );
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  async function handleRecording(blob: Blob, filename: string) {
    setUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      const file = new File([blob], filename, { type: blob.type });
      formData.append("file", file);

      const res = await fetch(`/api/v1/sessions/${sessionId}/recording`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);

      await apiFetch(`/v1/sessions/${sessionId}/transcribe`, { method: "POST" });
      router.push(`/sessions/${sessionId}`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleFilePick(file: File) {
    await handleRecording(file, file.name);
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-2xl">
        <p className="text-red-600">{loadError}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {session && (
        <Link
          href={`/patients/${session.patient_id}`}
          className="text-sm text-brand-700 hover:underline"
        >
          ← Back to patient
        </Link>
      )}
      <h1 className="text-2xl font-semibold">Record or upload session</h1>
      <p className="text-slate-600">
        Record in the browser, or upload an existing file (mp3, wav, webm, m4a).
        Transcription kicks off automatically after upload.
      </p>

      <div className="prose-surface">
        <h2 className="text-lg font-semibold">Record in browser</h2>
        <p className="mt-1 text-sm text-slate-600">
          Microphone is required. Audio is streamed to your browser only until
          upload.
        </p>
        <div className="mt-4">
          <AudioRecorder
            onComplete={(blob) =>
              handleRecording(blob, `session-${sessionId}.webm`)
            }
            disabled={uploading}
          />
        </div>
      </div>

      <div className="prose-surface">
        <h2 className="text-lg font-semibold">Upload a recording</h2>
        <input
          type="file"
          accept="audio/*"
          disabled={uploading}
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) await handleFilePick(f);
          }}
          className="mt-3 block w-full cursor-pointer rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      {uploading && (
        <p className="text-sm text-slate-600">
          Uploading and queuing transcription…
        </p>
      )}
      {uploadError && (
        <p className="text-sm text-red-600" role="alert">
          {uploadError}
        </p>
      )}
    </div>
  );
}
