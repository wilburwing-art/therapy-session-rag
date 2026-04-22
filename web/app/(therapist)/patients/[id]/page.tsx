import Link from "next/link";
import type { Assessment } from "@/lib/assessment";
import { serverFetch, serverFetchOrNull } from "@/lib/serverApi";
import type {
  ConversationSummary,
  CurrentUser,
  PatientThemes,
  SessionSummary,
} from "@/lib/types";
import { AssessmentPanel } from "./AssessmentPanel";
import { ConsentPanel } from "./ConsentPanel";
import { GenerateThemesButton } from "./GenerateThemesButton";
import { MagicLinkButton } from "./MagicLinkButton";
import { NewSessionButton } from "./NewSessionButton";

type PatientUser = {
  id: string;
  email: string;
  full_name: string | null;
};

type ConsentRecord = {
  id: string;
  patient_id: string;
  therapist_id: string;
  consent_type: "recording" | "transcription" | "ai_analysis";
  status: "granted" | "revoked";
  granted_at: string;
  revoked_at: string | null;
};

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await serverFetch<CurrentUser>("/api/v1/auth/me");
  const [patient, sessions, themes, conversations, consents, assessments] =
    await Promise.all([
      serverFetch<PatientUser>(`/api/v1/users/${id}`).catch(() => null),
      serverFetch<SessionSummary[]>(`/api/v1/sessions/patient/${id}`),
      serverFetchOrNull<PatientThemes>(`/api/v1/patients/${id}/themes`),
      serverFetch<ConversationSummary[]>(
        `/api/v1/patients/${id}/conversations?limit=10`,
      ),
      serverFetch<ConsentRecord[]>(
        `/api/v1/consent/${id}/active?therapist_id=${me.id}`,
      ).catch(() => [] as ConsentRecord[]),
      serverFetch<Assessment[]>(
        `/api/v1/patients/${id}/assessments?limit=50`,
      ).catch(() => [] as Assessment[]),
    ]);

  return (
    <div className="space-y-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">
            {patient?.full_name ?? patient?.email ?? "Patient"}
          </h1>
          {patient?.email && (
            <p className="mt-1 text-slate-600">{patient.email}</p>
          )}
        </div>
        <MagicLinkButton patientId={id} />
      </header>

      <ConsentPanel
        patientId={id}
        therapistId={me.id}
        activeConsents={consents}
      />

      <section>
        <h2 className="text-xl font-semibold">Outcome measures</h2>
        <div className="mt-4">
          <AssessmentPanel patientId={id} assessments={assessments} />
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Themes across sessions</h2>
          <GenerateThemesButton patientId={id} hasExisting={!!themes} />
        </div>
        {themes ? (
          <ThemesView themes={themes} />
        ) : (
          <p className="mt-4 text-slate-600">
            No themes synthesized yet. Need at least two sessions with recaps.
          </p>
        )}
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Sessions</h2>
          <NewSessionButton
            patientId={id}
            therapistId={me.id}
            activeConsents={consents}
          />
        </div>
        {sessions.length === 0 ? (
          <p className="mt-4 text-slate-600">No sessions yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white">
            {sessions.map((s) => (
              <li key={s.id}>
                <Link
                  href={`/sessions/${s.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
                >
                  <div>
                    <p className="font-medium">
                      {new Date(s.session_date).toLocaleString()}
                    </p>
                    <p className="text-sm text-slate-500">
                      Status: {s.status}
                      {s.recording_duration_seconds
                        ? ` · ${Math.round(s.recording_duration_seconds / 60)} min`
                        : ""}
                    </p>
                  </div>
                  <span className="text-sm text-brand-700">Open →</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-xl font-semibold">
          Between-session chatbot activity
        </h2>
        {conversations.length === 0 ? (
          <p className="mt-4 text-slate-600">
            The patient hasn&apos;t used the chatbot yet.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
            {conversations.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/patients/${id}/conversations/${c.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
                >
                  <div>
                    <p className="font-medium">
                      {c.title ?? "Untitled conversation"}
                    </p>
                    <p className="text-sm text-slate-500">
                      {c.message_count} message{c.message_count === 1 ? "" : "s"} ·
                      {" "}
                      {new Date(c.updated_at).toLocaleString()}
                    </p>
                  </div>
                  <span className="text-sm text-brand-700">Read →</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ThemesView({ themes }: { themes: PatientThemes }) {
  return (
    <div className="mt-4 grid gap-4 md:grid-cols-2">
      <Card title={`Recurring topics (${themes.recurring_topics.length})`}>
        {themes.recurring_topics.length === 0 ? (
          <p className="text-slate-500">None yet.</p>
        ) : (
          <ul className="space-y-2">
            {themes.recurring_topics.map((t) => (
              <li key={t.topic}>
                <p className="font-medium">
                  {t.topic}{" "}
                  <span className="text-sm font-normal text-slate-500">
                    · {t.session_count} session{t.session_count === 1 ? "" : "s"}
                  </span>
                </p>
                {t.summary && (
                  <p className="text-sm text-slate-600">{t.summary}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Emotional patterns">
        {themes.emotional_patterns.length === 0 ? (
          <p className="text-slate-500">None noted.</p>
        ) : (
          <ul className="space-y-2">
            {themes.emotional_patterns.map((p) => (
              <li key={p.pattern}>
                <p className="font-medium">{p.pattern}</p>
                {p.evidence && (
                  <p className="text-sm text-slate-600">{p.evidence}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Coping strategies">
        {themes.coping_strategies.length === 0 ? (
          <p className="text-slate-500">None discussed.</p>
        ) : (
          <ul className="space-y-2">
            {themes.coping_strategies.map((s) => (
              <li key={s.strategy}>
                <p className="font-medium">{s.strategy}</p>
                {s.notes && <p className="text-sm text-slate-600">{s.notes}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Ongoing concerns">
        {themes.ongoing_concerns.length === 0 ? (
          <p className="text-slate-500">None.</p>
        ) : (
          <ul className="list-disc pl-5 text-slate-800">
            {themes.ongoing_concerns.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        )}
      </Card>
      {themes.progress_indicators.length > 0 && (
        <Card title="Progress indicators">
          <ul className="list-disc pl-5 text-slate-800">
            {themes.progress_indicators.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      <div className="mt-3 text-slate-800">{children}</div>
    </div>
  );
}
