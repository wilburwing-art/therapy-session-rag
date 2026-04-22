"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type CreatedPatient = {
  id: string;
  email: string;
  full_name: string | null;
};

export default function NewPatientPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", full_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const patient = await apiFetch<CreatedPatient>("/v1/users/patients", {
        json: form,
      });
      router.push(`/patients/${patient.id}?created=1`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add patient");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <Link
        href="/dashboard"
        className="text-sm text-brand-700 hover:underline"
      >
        ← Back to patients
      </Link>
      <h1 className="mt-4 text-2xl font-semibold">Add a patient</h1>
      <p className="mt-1 text-sm text-slate-600">
        Patients don&apos;t need an account. You&apos;ll send them a one-time
        link whenever you want them to chat with their sessions.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <label className="block">
          <span className="block text-sm font-medium text-slate-700">
            Patient&apos;s name
          </span>
          <input
            type="text"
            required
            value={form.full_name}
            onChange={(e) =>
              setForm((f) => ({ ...f, full_name: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="block">
          <span className="block text-sm font-medium text-slate-700">
            Patient&apos;s email
          </span>
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) =>
              setForm((f) => ({ ...f, email: e.target.value }))
            }
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-brand-600 py-2 text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {submitting ? "Adding…" : "Add patient"}
        </button>
      </form>
    </div>
  );
}
