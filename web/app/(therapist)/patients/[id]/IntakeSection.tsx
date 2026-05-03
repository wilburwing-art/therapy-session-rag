"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export type IntakeFormSummary = {
  id: string;
  name: string;
  status: "draft" | "active" | "archived";
};

export type IntakeInvitationSummary = {
  id: string;
  form_id: string;
  patient_email: string;
  patient_name: string | null;
  status: "pending" | "submitted" | "expired" | "revoked";
  expires_at: string;
  submitted_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

type CreateInvitationResponse = {
  id: string;
  form_id: string;
  patient_email: string;
  token: string;
  expires_at: string;
  status: "pending" | "submitted" | "expired" | "revoked";
};

const STATUS_LABELS: Record<IntakeInvitationSummary["status"], string> = {
  pending: "Pending",
  submitted: "Submitted",
  expired: "Expired",
  revoked: "Revoked",
};

const STATUS_STYLES: Record<IntakeInvitationSummary["status"], string> = {
  pending: "bg-amber-100 text-amber-900",
  submitted: "bg-emerald-100 text-emerald-900",
  expired: "bg-slate-200 text-slate-700",
  revoked: "bg-slate-200 text-slate-700",
};

export function IntakeSection({
  patientEmail,
  forms,
  invitations,
}: {
  patientEmail: string | null;
  forms: IntakeFormSummary[];
  invitations: IntakeInvitationSummary[];
}) {
  const router = useRouter();
  const activeForms = forms.filter((f) => f.status === "active");
  const [formId, setFormId] = useState<string>(activeForms[0]?.id ?? "");
  const [sharedLink, setSharedLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function issueInvitation() {
    if (!patientEmail) {
      setError("Patient needs an email on file before sending intake.");
      return;
    }
    if (!formId) {
      setError("Select an active intake form to send.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSharedLink(null);
    try {
      const res = await apiFetch<CreateInvitationResponse>(
        "/v1/intake/invitations",
        {
          json: {
            form_id: formId,
            patient_email: patientEmail,
          },
        },
      );
      const origin =
        typeof window !== "undefined" ? window.location.origin : "";
      setSharedLink(`${origin}/intake?t=${encodeURIComponent(res.token)}`);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't send intake invitation",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function revoke(invitationId: string) {
    setError(null);
    try {
      await apiFetch(`/v1/intake/invitations/${invitationId}`, {
        method: "DELETE",
      });
      router.refresh();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't revoke invitation",
      );
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Intake forms</h2>
          <p className="mt-1 text-sm text-slate-600">
            Send an intake questionnaire before the first session. Answers
            feed into the recap generated after the session.
          </p>
        </div>
      </div>

      {activeForms.length === 0 ? (
        <p className="mt-4 text-sm text-slate-600">
          No active intake forms for your practice yet. Create one in Settings
          before sending invitations.
        </p>
      ) : (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-sm text-slate-700">
            <span className="text-xs uppercase tracking-wide text-slate-500">
              Form
            </span>
            <select
              value={formId}
              onChange={(e) => setFormId(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            >
              {activeForms.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={issueInvitation}
            disabled={submitting || !patientEmail}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "Sending…" : "Send intake"}
          </button>
          {!patientEmail && (
            <p className="text-xs text-slate-500">
              Add an email to this patient to enable intake invitations.
            </p>
          )}
        </div>
      )}

      {sharedLink && (
        <div className="mt-4 max-w-xl rounded-md bg-slate-100 p-3 text-xs text-slate-700">
          <p className="mb-1 font-medium">
            Copy this link if the email doesn&apos;t arrive:
          </p>
          <code className="break-all">{sharedLink}</code>
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {invitations.length > 0 && (
        <ul className="mt-5 divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200">
          {invitations.map((inv) => {
            const form = forms.find((f) => f.id === inv.form_id);
            return (
              <li
                key={inv.id}
                className="flex items-center justify-between gap-3 bg-white px-4 py-3"
              >
                <div>
                  <p className="font-medium">
                    {form?.name ?? "Unknown form"}
                    <span
                      className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[inv.status]}`}
                    >
                      {STATUS_LABELS[inv.status]}
                    </span>
                  </p>
                  <p className="text-xs text-slate-500">
                    Sent {new Date(inv.created_at).toLocaleString()}
                    {inv.submitted_at
                      ? ` · submitted ${new Date(inv.submitted_at).toLocaleString()}`
                      : ` · expires ${new Date(inv.expires_at).toLocaleString()}`}
                  </p>
                </div>
                {inv.status === "pending" && (
                  <button
                    onClick={() => revoke(inv.id)}
                    className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    Revoke
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
