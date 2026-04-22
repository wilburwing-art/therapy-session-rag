"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type AcceptState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string };

function AcceptInviteInner() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [form, setForm] = useState({ password: "", full_name: "" });
  const [state, setState] = useState<AcceptState>({ kind: "idle" });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("t");
    setToken(t);
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setState({ kind: "submitting" });
    try {
      await apiFetch("/v1/invites/accept", {
        json: {
          token,
          password: form.password,
          full_name: form.full_name,
        },
      });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 401
            ? "This invite is invalid, expired, or already accepted."
            : err.message
          : "Something went wrong accepting the invite.";
      setState({ kind: "error", message });
    }
  }

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  if (token === null) {
    return (
      <main className="mx-auto max-w-md px-6 py-16">
        <p className="text-slate-600">Loading…</p>
      </main>
    );
  }

  if (token === "") {
    return (
      <main className="mx-auto max-w-md px-6 py-16">
        <h1 className="text-2xl font-semibold">Invite link is missing a token</h1>
        <p className="mt-4 text-sm text-slate-600">
          Double-check the link in your invite email or ask the person who
          invited you to resend it.
        </p>
        <Link
          href="/login"
          className="mt-6 inline-block text-sm text-brand-700 hover:underline"
        >
          Back to sign in
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-2xl font-semibold">Accept your invite</h1>
      <p className="mt-2 text-sm text-slate-600">
        Set a password to finish joining the practice. We&apos;ll sign you in
        once you&apos;re done.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <label className="block">
          <span className="block text-sm font-medium text-slate-700">
            Your name
          </span>
          <input
            type="text"
            required
            value={form.full_name}
            onChange={(e) => set("full_name", e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="block">
          <span className="block text-sm font-medium text-slate-700">
            Password (min 8 chars)
          </span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => set("password", e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        {state.kind === "error" && (
          <p role="alert" className="text-sm text-red-600">
            {state.message}
          </p>
        )}
        <button
          type="submit"
          disabled={state.kind === "submitting"}
          className="w-full rounded-md bg-brand-600 py-2 text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {state.kind === "submitting" ? "Setting up…" : "Accept invite"}
        </button>
      </form>
      <p className="mt-6 text-sm text-slate-500">
        Already have an account?{" "}
        <Link href="/login" className="text-brand-700 hover:underline">
          Sign in
        </Link>
      </p>
    </main>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<p className="p-6 text-slate-600">Loading…</p>}>
      <AcceptInviteInner />
    </Suspense>
  );
}
