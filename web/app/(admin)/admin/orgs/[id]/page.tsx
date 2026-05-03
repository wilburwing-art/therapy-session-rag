import Link from "next/link";
import { serverFetch } from "@/lib/serverApi";
import { OrgActionButtons } from "../OrgActionButtons";

type SessionCounts = {
  pending: number;
  uploaded: number;
  transcribing: number;
  embedding: number;
  ready: number;
  failed: number;
};

type AdminUser = {
  id: string;
  email: string;
  role: string;
  full_name: string | null;
  created_at: string;
  email_verified_at: string | null;
};

type OrgAdminDetail = {
  id: string;
  name: string;
  created_at: string;
  subscription_status: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  trial_ends_at: string | null;
  current_period_end: string | null;
  disabled_at: string | null;
  users: AdminUser[];
  session_counts: SessionCounts;
};

export default async function AdminOrgDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const org = await serverFetch<OrgAdminDetail>(`/api/v1/admin/orgs/${id}`);
  const disabled = org.disabled_at !== null;

  return (
    <div className="space-y-8">
      <div>
        <Link
          href="/admin/orgs"
          className="text-sm text-brand-700 hover:underline"
        >
          ← Back to orgs
        </Link>
      </div>

      <header className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-3xl font-semibold">{org.name}</h1>
          <p className="mt-1 text-sm text-slate-600">
            Created {new Date(org.created_at).toLocaleString()}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <span
              className={
                disabled
                  ? "rounded-full bg-red-100 px-3 py-1 text-xs font-medium text-red-800"
                  : "rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800"
              }
            >
              {disabled ? "Suspended" : "Active"}
            </span>
            <span className="text-xs uppercase tracking-wide text-slate-500">
              {org.subscription_status}
            </span>
          </div>
        </div>
        <OrgActionButtons orgId={org.id} disabled={disabled} />
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        <Card title="Subscription">
          <dl className="space-y-2 text-sm">
            <Row label="Stripe customer" value={org.stripe_customer_id} />
            <Row
              label="Stripe subscription"
              value={org.stripe_subscription_id}
            />
            <Row
              label="Trial ends"
              value={
                org.trial_ends_at
                  ? new Date(org.trial_ends_at).toLocaleString()
                  : null
              }
            />
            <Row
              label="Current period end"
              value={
                org.current_period_end
                  ? new Date(org.current_period_end).toLocaleString()
                  : null
              }
            />
            <Row
              label="Disabled at"
              value={
                org.disabled_at
                  ? new Date(org.disabled_at).toLocaleString()
                  : null
              }
            />
          </dl>
        </Card>
        <Card title="Session counts">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <StatRow label="Pending" value={org.session_counts.pending} />
            <StatRow label="Uploaded" value={org.session_counts.uploaded} />
            <StatRow
              label="Transcribing"
              value={org.session_counts.transcribing}
            />
            <StatRow label="Embedding" value={org.session_counts.embedding} />
            <StatRow label="Ready" value={org.session_counts.ready} />
            <StatRow label="Failed" value={org.session_counts.failed} />
          </dl>
        </Card>
      </section>

      <section>
        <h2 className="text-xl font-semibold">
          Users ({org.users.length})
        </h2>
        {org.users.length === 0 ? (
          <p className="mt-3 text-slate-600">No users.</p>
        ) : (
          <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Email verified</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {org.users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">
                        {u.full_name ?? u.email}
                      </p>
                      <p className="text-xs text-slate-500">{u.email}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{u.role}</td>
                    <td className="px-4 py-3 text-slate-600">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {u.email_verified_at
                        ? new Date(u.email_verified_at).toLocaleDateString()
                        : "Not verified"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      <div className="mt-3 text-slate-800">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right text-slate-800">{value ?? "—"}</dd>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd className="tabular-nums text-slate-800">{value}</dd>
    </div>
  );
}
