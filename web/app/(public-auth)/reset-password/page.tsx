"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

function ResetPasswordInner() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("t"));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("This link is missing its token. Request a new one.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/v1/auth/password-reset-confirm", {
        json: { token, new_password: password },
      });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reset");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-6 sm:py-20">
      <h1 className="text-2xl font-semibold">Choose a new password</h1>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <label className="block">
          <span className="block text-sm font-medium text-slate-700">
            New password (min 8 chars)
          </span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="block">
          <span className="block text-sm font-medium text-slate-700">Confirm</span>
          <input
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
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
          {submitting ? "Saving…" : "Set new password"}
        </button>
      </form>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<p className="p-6 text-slate-600">Loading…</p>}>
      <ResetPasswordInner />
    </Suspense>
  );
}
