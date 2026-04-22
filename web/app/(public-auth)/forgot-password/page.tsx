"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/v1/auth/password-reset-request", { json: { email } });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-6 sm:py-20">
      <h1 className="text-2xl font-semibold">Reset your password</h1>
      {done ? (
        <div className="mt-4 rounded-md bg-slate-100 p-4 text-slate-700">
          <p>
            If there&apos;s an account for <strong>{email}</strong>, we sent a
            reset link. Check your inbox — the link expires in 30 minutes.
          </p>
          <Link
            href="/login"
            className="mt-4 inline-block text-sm text-brand-700 hover:underline"
          >
            Back to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <label className="block">
            <span className="block text-sm font-medium text-slate-700">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
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
            className="w-full rounded-md bg-brand-600 py-3 text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "Sending…" : "Send reset link"}
          </button>
          <p className="text-sm text-slate-600">
            Remembered it?{" "}
            <Link href="/login" className="font-medium text-brand-700 hover:underline">
              Back to sign in
            </Link>
          </p>
        </form>
      )}
    </main>
  );
}
