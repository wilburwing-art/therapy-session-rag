"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type Enroll2FAResponse = {
  provisioning_uri: string;
  secret: string;
};

type Phase =
  | { kind: "idle" }
  | { kind: "enrolled"; provisioning_uri: string; secret: string }
  | { kind: "active" }
  | { kind: "disabling" };

export function SecurityForm() {
  // Phase state drives the UI: start neutral, then branch into either
  // an enrollment flow (pending activation) or an "already active"
  // view. We discover which one by calling /2fa/enroll — a 409 means
  // it's already active and we skip straight to the disable view.
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function startEnrollment() {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch<Enroll2FAResponse>("/v1/auth/2fa/enroll", {
        method: "POST",
      });
      setPhase({
        kind: "enrolled",
        provisioning_uri: res.provisioning_uri,
        secret: res.secret,
      });
    } catch (err) {
      // 409 Conflict → 2FA already on.
      if (err instanceof ApiError && err.status === 409) {
        setPhase({ kind: "active" });
      } else {
        setError(
          err instanceof ApiError ? err.message : "Could not start enrollment",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  async function activate() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/v1/auth/2fa/activate", { json: { code } });
      setPhase({ kind: "active" });
      setCode("");
      setInfo("2FA is now active on your account.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not activate 2FA");
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/v1/auth/2fa/disable", {
        json: { code, password },
      });
      setPhase({ kind: "idle" });
      setCode("");
      setPassword("");
      setInfo("2FA has been disabled.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disable 2FA");
    } finally {
      setBusy(false);
    }
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setInfo("Copied to clipboard.");
    } catch {
      // Fallback: the value is already visible on-screen for manual copy.
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-medium text-slate-900">
        Two-factor authentication
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Require a 6-digit code from an authenticator app each time you sign in.
      </p>

      {phase.kind === "idle" && (
        <div className="mt-4">
          <button
            type="button"
            onClick={startEnrollment}
            disabled={busy}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "Starting…" : "Enroll in 2FA"}
          </button>
        </div>
      )}

      {phase.kind === "enrolled" && (
        <div className="mt-4 space-y-4">
          <div className="rounded-md bg-slate-50 p-4 text-sm">
            <p className="font-medium text-slate-900">
              Step 1. Add this account to your authenticator
            </p>
            <p className="mt-1 text-slate-600">
              Paste this URL into your authenticator, or open it in a QR
              generator of your choice. If you&apos;d rather type the secret
              yourself, use the key below.
            </p>
            <div className="mt-3 space-y-2">
              <a
                href={phase.provisioning_uri}
                className="block truncate text-xs text-brand-700 underline"
              >
                {phase.provisioning_uri}
              </a>
              <div className="flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-white px-2 py-1 text-xs text-slate-800">
                  {phase.provisioning_uri}
                </code>
                <button
                  type="button"
                  onClick={() => copyToClipboard(phase.provisioning_uri)}
                  className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                >
                  Copy URI
                </button>
              </div>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded bg-white px-2 py-1 text-xs tracking-widest text-slate-800">
                  {phase.secret}
                </code>
                <button
                  type="button"
                  onClick={() => copyToClipboard(phase.secret)}
                  className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                >
                  Copy secret
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-md bg-slate-50 p-4 text-sm">
            <label
              htmlFor="activate-code"
              className="block font-medium text-slate-900"
            >
              Step 2. Enter a 6-digit code from your authenticator
            </label>
            <div className="mt-2 flex gap-2">
              <input
                id="activate-code"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm tracking-widest"
              />
              <button
                type="button"
                onClick={activate}
                disabled={busy || code.length < 6}
                className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {busy ? "Verifying…" : "Activate"}
              </button>
            </div>
          </div>
        </div>
      )}

      {phase.kind === "active" && (
        <div className="mt-4 space-y-4">
          <p className="rounded-md bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            2FA is active on this account.
          </p>
          <div className="rounded-md bg-slate-50 p-4 text-sm">
            <p className="font-medium text-slate-900">Disable 2FA</p>
            <p className="mt-1 text-slate-600">
              Enter your password and a current 6-digit code to remove 2FA.
            </p>
            <div className="mt-3 space-y-2">
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Current password"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <div className="flex gap-2">
                <input
                  inputMode="numeric"
                  pattern="[0-9]*"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="123456"
                  className="w-32 rounded-md border border-slate-300 px-3 py-2 text-sm tracking-widest"
                />
                <button
                  type="button"
                  onClick={disable}
                  disabled={busy || code.length < 6 || password.length === 0}
                  className="rounded-md border border-red-300 bg-white px-4 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  {busy ? "Disabling…" : "Disable 2FA"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error}
        </p>
      )}
      {info && !error && (
        <p className="mt-4 text-sm text-emerald-700">{info}</p>
      )}
    </section>
  );
}
