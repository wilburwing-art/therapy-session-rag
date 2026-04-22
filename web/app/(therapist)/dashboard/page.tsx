import Link from "next/link";
import { serverFetch, serverFetchOrNull } from "@/lib/serverApi";

type PatientUser = {
  id: string;
  email: string;
  role: string;
  full_name: string | null;
  created_at: string;
};

// analytics-engineer: quick-stats row
type ActivePatientsResponse = {
  window_days: number;
  active_patients: number;
};

type SessionsByWeekPoint = {
  week_start: string;
  count: number;
};

export default async function DashboardPage() {
  const [patients, activePatients, sessionsByWeek] = await Promise.all([
    serverFetch<PatientUser[]>("/api/v1/users?role=patient"),
    serverFetchOrNull<ActivePatientsResponse>(
      "/api/v1/analytics/therapist/active-patients?days=30",
    ),
    serverFetchOrNull<SessionsByWeekPoint[]>(
      "/api/v1/analytics/therapist/sessions-by-week?weeks_back=1",
    ),
  ]);

  const sessionsThisWeek = sessionsByWeek?.[sessionsByWeek.length - 1]?.count ?? 0;

  return (
    <div className="space-y-8">
      {/* analytics-engineer: quick-stats row */}
      {(activePatients || sessionsByWeek) && (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Active patients (30d)
            </p>
            <p className="mt-1 text-3xl font-semibold text-slate-900">
              {activePatients?.active_patients ?? 0}
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Sessions this week
                </p>
                <p className="mt-1 text-3xl font-semibold text-slate-900">
                  {sessionsThisWeek}
                </p>
              </div>
              <Link
                href="/analytics"
                className="text-sm text-brand-700 hover:underline"
              >
                View analytics →
              </Link>
            </div>
          </div>
        </section>
      )}

      <header className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-2xl font-semibold sm:text-3xl">Patients</h1>
          <p className="mt-1 text-slate-600">
            {patients.length} active patient{patients.length === 1 ? "" : "s"}
          </p>
        </div>
        <Link
          href="/patients/new"
          className="w-full rounded-md bg-brand-600 px-4 py-3 text-center text-sm text-white hover:bg-brand-700 sm:w-auto sm:py-2"
        >
          + Add patient
        </Link>
      </header>

      {patients.length === 0 ? (
        <div className="prose-surface text-center">
          <p className="text-slate-600">
            No patients yet. Add your first patient to start recording sessions.
          </p>
          <Link
            href="/patients/new"
            className="mt-4 inline-block rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700"
          >
            Add your first patient
          </Link>
        </div>
      ) : (
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {patients.map((p) => (
            <li key={p.id}>
              <Link
                href={`/patients/${p.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
              >
                <div>
                  <p className="font-medium text-slate-900">
                    {p.full_name ?? p.email}
                  </p>
                  <p className="text-sm text-slate-500">{p.email}</p>
                </div>
                <span className="text-sm text-brand-700">View →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
