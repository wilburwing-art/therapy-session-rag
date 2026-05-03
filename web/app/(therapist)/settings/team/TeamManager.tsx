"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type InviteSummary = {
  id: string;
  email: string;
  role: "therapist" | "admin";
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
};

type InviteCreateResponse = {
  id: string;
  email: string;
  role: "therapist" | "admin";
  token: string;
  expires_at: string;
};

type Toast =
  | { kind: "success"; email: string; copyUrl: string | null }
  | { kind: "error"; message: string };

export function TeamManager({
  initialPending,
}: {
  initialPending: InviteSummary[];
}) {
  const router = useRouter();
  const [pending, setPending] = useState<InviteSummary[]>(initialPending);
  const [form, setForm] = useState<{
    email: string;
    role: "therapist" | "admin";
  }>({
    email: "",
    role: "therapist",
  });
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setToast(null);
    try {
      const created = await apiFetch<InviteCreateResponse>("/v1/invites", {
        json: { email: form.email, role: form.role },
      });
      const copyUrl = `${window.location.origin}/accept-invite?t=${created.token}`;
      setPending((prev) => [
        {
          id: created.id,
          email: created.email,
          role: created.role,
          expires_at: created.expires_at,
          accepted_at: null,
          created_at: new Date().toISOString(),
        },
        ...prev,
      ]);
      setForm({ email: "", role: "therapist" });
      setToast({ kind: "success", email: created.email, copyUrl });
      router.refresh();
    } catch (err) {
      setToast({
        kind: "error",
        message:
          err instanceof ApiError ? err.message : "Could not send invite",
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function onRevoke(invite: InviteSummary) {
    const confirmed = window.confirm(
      `Revoke the invite for ${invite.email}? They won't be able to join with this link.`,
    );
    if (!confirmed) return;
    setRevoking(invite.id);
    setToast(null);
    try {
      await apiFetch(`/v1/invites/${invite.id}`, { method: "DELETE" });
      setPending((prev) => prev.filter((p) => p.id !== invite.id));
      router.refresh();
    } catch (err) {
      setToast({
        kind: "error",
        message:
          err instanceof ApiError ? err.message : "Could not revoke invite",
      });
    } finally {
      setRevoking(null);
    }
  }

  async function copyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // Ignore — fallback is the visible URL in the toast.
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-medium text-slate-900">
          Invite a therapist
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          They&apos;ll get an email with a link to set a password and join your
          practice.
        </p>
        <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input
            type="email"
            required
            placeholder="colleague@example.com"
            value={form.email}
            onChange={(e) =>
              setForm((f) => ({ ...f, email: e.target.value }))
            }
            className="flex-1 rounded-md border border-slate-300 px-3 py-2"
          />
          <select
            value={form.role}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                role: e.target.value as "therapist" | "admin",
              }))
            }
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="therapist">Therapist</option>
            <option value="admin">Admin</option>
          </select>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "Sending…" : "Send invite"}
          </button>
        </form>
        {toast && toast.kind === "success" && (
          <div className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">
            <p>
              Invite sent to <strong>{toast.email}</strong>.
            </p>
            {toast.copyUrl && (
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-white px-2 py-1 text-xs text-slate-700">
                  {toast.copyUrl}
                </code>
                <button
                  type="button"
                  onClick={() => copyLink(toast.copyUrl as string)}
                  className="rounded-md border border-emerald-300 bg-white px-2 py-1 text-xs text-emerald-900 hover:bg-emerald-50"
                >
                  Copy link
                </button>
              </div>
            )}
            <p className="mt-2 text-xs text-emerald-800">
              Copy the link if the email doesn&apos;t arrive — it won&apos;t be
              shown again.
            </p>
          </div>
        )}
        {toast && toast.kind === "error" && (
          <p className="mt-3 text-sm text-red-600">{toast.message}</p>
        )}
      </div>

      {pending.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-900">
            Pending invites ({pending.length})
          </h3>
          <ul className="mt-2 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            {pending.map((inv) => (
              <li
                key={inv.id}
                className="flex items-center justify-between px-5 py-4 text-sm"
              >
                <div>
                  <p className="font-medium text-slate-900">{inv.email}</p>
                  <p className="text-xs text-slate-500">
                    Expires {new Date(inv.expires_at).toLocaleDateString()} ·{" "}
                    {inv.role}
                  </p>
                </div>
                <button
                  onClick={() => onRevoke(inv)}
                  disabled={revoking === inv.id}
                  className="rounded-md border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  {revoking === inv.id ? "Revoking…" : "Revoke"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
