import { serverFetch } from "@/lib/serverApi";
import { TeamManager } from "./TeamManager";

type TherapistUser = {
  id: string;
  email: string;
  role: string;
  full_name: string | null;
  created_at: string;
};

type Invite = {
  id: string;
  organization_id: string;
  invited_by_user_id: string;
  email: string;
  role: "therapist" | "admin";
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
};

export default async function TeamPage() {
  const [therapists, invites] = await Promise.all([
    serverFetch<TherapistUser[]>("/api/v1/users?role=therapist"),
    serverFetch<Invite[]>("/api/v1/invites"),
  ]);

  const pending = invites.filter((i) => i.accepted_at === null);
  const accepted = invites.filter((i) => i.accepted_at !== null);

  return (
    <div className="max-w-3xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Team</h1>
        <p className="mt-1 text-sm text-slate-600">
          Invite other therapists and manage who has access to this practice.
        </p>
      </header>

      <TeamManager initialPending={pending} />

      <section>
        <h2 className="text-lg font-medium text-slate-900">
          Therapists ({therapists.length})
        </h2>
        <ul className="mt-3 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {therapists.map((t) => (
            <li
              key={t.id}
              className="flex items-center justify-between px-5 py-4"
            >
              <div>
                <p className="font-medium text-slate-900">
                  {t.full_name ?? t.email}
                </p>
                <p className="text-sm text-slate-500">{t.email}</p>
              </div>
              <span className="text-xs uppercase tracking-wide text-slate-400">
                {t.role}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {accepted.length > 0 && (
        <section>
          <h2 className="text-lg font-medium text-slate-900">
            Accepted invites
          </h2>
          <ul className="mt-3 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            {accepted.map((inv) => (
              <li
                key={inv.id}
                className="flex items-center justify-between px-5 py-4 text-sm"
              >
                <div>
                  <p className="font-medium text-slate-900">{inv.email}</p>
                  <p className="text-xs text-slate-500">
                    Accepted{" "}
                    {inv.accepted_at
                      ? new Date(inv.accepted_at).toLocaleDateString()
                      : ""}
                  </p>
                </div>
                <span className="text-xs uppercase tracking-wide text-slate-400">
                  {inv.role}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
