import Link from "next/link";
import { SessionPlayer } from "@/components/SessionPlayer";
import { serverFetch, serverFetchOrNull } from "@/lib/serverApi";
import type {
  SessionRead,
  SessionRecap,
  TranscriptSegment,
} from "@/lib/types";
import { NotesEditor } from "./NotesEditor";
import { RecapActions } from "./RecapActions";

type Transcript = {
  id: string;
  full_text: string;
  word_count: number | null;
  duration_seconds: number | null;
  language: string | null;
  segments: TranscriptSegment[];
};

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [session, transcript, recap] = await Promise.all([
    serverFetch<SessionRead>(`/api/v1/sessions/${id}`),
    serverFetchOrNull<Transcript>(`/api/v1/sessions/${id}/transcript`),
    serverFetchOrNull<SessionRecap>(`/api/v1/sessions/${id}/recap`),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <Link
          href={`/patients/${session.patient_id}`}
          className="text-sm text-brand-700 hover:underline"
        >
          ← Back to patient
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">
          Session on {new Date(session.session_date).toLocaleString()}
        </h1>
        <p className="mt-1 text-slate-600">
          Status: <span className="font-medium">{session.status}</span>
        </p>
      </header>

      <NotesEditor sessionId={id} initialNotes={session.therapist_notes ?? ""} />

      <section className="prose-surface">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recap</h2>
          <RecapActions sessionId={id} hasExisting={!!recap} />
        </div>
        {recap ? (
          <div className="mt-4 space-y-4">
            <p className="text-slate-800">{recap.brief}</p>
            {recap.emotional_tone && (
              <p className="text-sm text-slate-600">
                Tone: {recap.emotional_tone}
              </p>
            )}
            {recap.key_topics.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-slate-700">
                  Key topics
                </h3>
                <div className="mt-1 flex flex-wrap gap-2">
                  {recap.key_topics.map((t) => (
                    <span
                      key={t}
                      className="rounded-full bg-brand-50 px-3 py-1 text-sm text-brand-900"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {recap.homework_assigned.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-slate-700">
                  Homework
                </h3>
                <ul className="mt-1 list-disc pl-5">
                  {recap.homework_assigned.map((h, i) => (
                    <li key={i} className="text-slate-800">
                      {h.task}
                      {h.notes && (
                        <span className="text-slate-500"> — {h.notes}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recap.follow_ups.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-slate-700">
                  Follow up next session
                </h3>
                <ul className="mt-1 list-disc pl-5">
                  {recap.follow_ups.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            {recap.risk_flags.length > 0 && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3">
                <h3 className="text-sm font-semibold text-red-900">
                  Risk flags for review
                </h3>
                <ul className="mt-1 list-disc pl-5 text-red-900">
                  {recap.risk_flags.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="mt-3 text-slate-600">
            No recap yet. It&apos;ll appear automatically once embedding
            completes.
          </p>
        )}
      </section>

      <section className="prose-surface">
        <h2 className="text-lg font-semibold">Transcript</h2>
        {transcript ? (
          <>
            <p className="mt-2 text-sm text-slate-500">
              {transcript.word_count ?? "?"} words
              {transcript.duration_seconds
                ? ` · ${Math.round(transcript.duration_seconds / 60)} min`
                : ""}
            </p>
            <div className="mt-4">
              <SessionPlayer
                sessionId={id}
                segments={transcript.segments ?? []}
                fallbackText={transcript.full_text ?? ""}
              />
            </div>
          </>
        ) : (
          <p className="mt-2 text-slate-600">
            Transcript not available yet.
          </p>
        )}
      </section>
    </div>
  );
}
