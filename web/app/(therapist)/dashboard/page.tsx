import Link from "next/link";
import { serverFetch } from "@/lib/serverApi";

type PatientUser = {
  id: string;
  email: string;
  role: string;
  full_name: string | null;
  created_at: string;
};

export default async function DashboardPage() {
  const patients = await serverFetch<PatientUser[]>(
    "/api/v1/users?role=patient",
  );

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Patients</h1>
          <p className="mt-1 text-slate-600">
            {patients.length} active patient{patients.length === 1 ? "" : "s"}
          </p>
        </div>
        <Link
          href="/patients/new"
          className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700"
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
