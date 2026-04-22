"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type LoginResponse = {
  user_id: string;
  organization_id: string;
  email: string;
  full_name: string | null;
  expires_at: string;
};

type LoginChallengeResponse = {
  requires_2fa: true;
  challenge_token: string;
  expires_at: string;
};

// The login endpoint returns either a session (cookie set) or a 2FA
// challenge. Discriminate on `requires_2fa` so the UI knows whether to
// redirect or prompt for a code.
function isChallengeResponse(
  body: LoginResponse | LoginChallengeResponse,
): body is LoginChallengeResponse {
  return "requires_2fa" in body && body.requires_2fa === true;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 2FA challenge state. `challengeToken` is held in component state
  // only — deliberately NOT in a cookie. The backend will reject an
  // expired token; on a fresh tab reload we simply start over.
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [code, setCode] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body = await apiFetch<LoginResponse | LoginChallengeResponse>(
        "/v1/auth/login",
        { json: { email, password } },
      );
      if (isChallengeResponse(body)) {
        setChallengeToken(body.challenge_token);
        setCode("");
        return;
      }
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function onSubmitChallenge(e: React.FormEvent) {
    e.preventDefault();
    if (!challengeToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await apiFetch("/v1/auth/2fa/challenge", {
        json: { challenge_token: challengeToken, code },
      });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verification failed");
    } finally {
      setSubmitting(false);
    }
  }

  function cancelChallenge() {
    setChallengeToken(null);
    setCode("");
    setError(null);
  }

  if (challengeToken) {
    return (
      <main className="mx-auto max-w-md px-6 py-20">
        <h1 className="text-2xl font-semibold">Enter your 2FA code</h1>
        <p className="mt-2 text-sm text-slate-600">
          Open your authenticator app and enter the 6-digit code for this
          account.
        </p>
        <form onSubmit={onSubmitChallenge} className="mt-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">
              Authentication code
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-lg tracking-widest shadow-sm focus:border-brand-500 focus:ring-brand-500"
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting || code.length < 6}
            className="w-full rounded-md bg-brand-600 py-2 text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "Verifying…" : "Verify and sign in"}
          </button>
          <button
            type="button"
            onClick={cancelChallenge}
            className="w-full text-sm text-slate-500 hover:text-slate-700"
          >
            Cancel and sign in again
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-md px-6 py-20">
      <h1 className="text-2xl font-semibold">Therapist login</h1>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700">Email</label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-brand-500 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700">Password</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm focus:border-brand-500 focus:ring-brand-500"
          />
        </div>
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
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-6 text-sm text-slate-600">
        New practice?{" "}
        <Link href="/signup" className="font-medium text-brand-700 hover:underline">
          Start a 14-day trial
        </Link>
      </p>
      <p className="mt-1 text-sm text-slate-500">
        <Link
          href="/forgot-password"
          className="hover:text-slate-700 hover:underline"
        >
          Forgot your password?
        </Link>
      </p>
    </main>
  );
}
