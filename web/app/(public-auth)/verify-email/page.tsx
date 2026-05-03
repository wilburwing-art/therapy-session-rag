"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

function VerifyEmailInner() {
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "ok" } | { kind: "error"; message: string }
  >({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(window.location.search);
    const token = params.get("t");
    if (!token) {
      setState({ kind: "error", message: "This link is missing its token." });
      return;
    }
    apiFetch("/v1/auth/verify-email-confirm", { json: { token } })
      .then(() => !cancelled && setState({ kind: "ok" }))
      .catch((err) => {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            err instanceof ApiError
              ? err.message
              : "The link may be expired or already used.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-6 sm:py-20">
      <h1 className="text-2xl font-semibold">Email verification</h1>
      <div className="mt-6 rounded-md bg-white p-5 shadow-sm">
        {state.kind === "loading" && (
          <p className="text-slate-600">Verifying your email…</p>
        )}
        {state.kind === "ok" && (
          <div>
            <p className="text-emerald-800">Your email is verified. Thanks!</p>
            <Link
              href="/dashboard"
              className="mt-4 inline-block text-sm text-brand-700 hover:underline"
            >
              Go to dashboard →
            </Link>
          </div>
        )}
        {state.kind === "error" && (
          <div>
            <p className="text-red-700">{state.message}</p>
            <Link
              href="/dashboard"
              className="mt-4 inline-block text-sm text-brand-700 hover:underline"
            >
              Back to dashboard
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<p className="p-6 text-slate-600">Loading…</p>}>
      <VerifyEmailInner />
    </Suspense>
  );
}
