"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError } from "@/lib/api";
import { register } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    practice_name: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(form);
      router.push("/billing?new=true");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <main className="mx-auto max-w-md px-4 py-10 sm:px-6 sm:py-16">
      <h1 className="text-2xl font-semibold">Start your 14-day trial</h1>
      <p className="mt-2 text-sm text-slate-600">
        No credit card needed today. $149/mo when your trial ends.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <Field label="Your name">
          <input
            type="text"
            required
            value={form.full_name}
            onChange={(e) => set("full_name", e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label="Practice name">
          <input
            type="text"
            required
            value={form.practice_name}
            onChange={(e) => set("practice_name", e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label="Work email">
          <input
            type="email"
            required
            autoComplete="email"
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        <Field label="Password (min 8 chars)">
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => set("password", e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </Field>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-brand-600 py-3 text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {submitting ? "Creating your account…" : "Create account"}
        </button>
      </form>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-slate-700">{label}</span>
      <span className="mt-1 block">{children}</span>
    </label>
  );
}
