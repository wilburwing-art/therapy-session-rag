import Link from "next/link";
import { serverFetch } from "@/lib/serverApi";
import { OrgActionButtons } from "./OrgActionButtons";

type OrgAdminView = {
  id: string;
  name: string;
  created_at: string;
  subscription_status: string;
  disabled_at: string | null;
  user_count: number;
  session_count: number;
};

export default async function AdminOrgsPage() {
  const orgs = await serverFetch<OrgAdminView[]>("/api/v1/admin/orgs");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold">Organizations</h1>
        <p className="mt-1 text-slate-600">
          {orgs.length} organization{orgs.length === 1 ? "" : "s"}
        </p>
      </header>

      {orgs.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600">
          No organizations yet.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Subscription</th>
                <th className="px-4 py-3 text-right">Users</th>
                <th className="px-4 py-3 text-right">Sessions</th>
                <th className="px-4 py-3">Disabled?</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {orgs.map((org) => {
                const disabled = org.disabled_at !== null;
                return (
                  <tr key={org.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/orgs/${org.id}`}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {org.name}
                      </Link>
                      <p className="text-xs text-slate-500">
                        Created {new Date(org.created_at).toLocaleDateString()}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          disabled
                            ? "rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800"
                            : "rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800"
                        }
                      >
                        {disabled ? "Suspended" : "Active"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      {org.subscription_status}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                      {org.user_count}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                      {org.session_count}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {org.disabled_at
                        ? new Date(org.disabled_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <OrgActionButtons
                        orgId={org.id}
                        disabled={disabled}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
