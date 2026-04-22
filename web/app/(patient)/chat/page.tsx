"use client";

import { useEffect, useState } from "react";
import { ChatSurface } from "@/components/ChatSurface";
import { ApiError } from "@/lib/api";
import { currentPatient, redeemMagicLink } from "@/lib/auth";
import type { CurrentPatient } from "@/lib/types";

export default function PatientChatPage() {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "ready"; patient: CurrentPatient }
    | { kind: "needs_link" }
    | { kind: "redeeming" }
    | { kind: "error"; message: string }
  >({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const params = new URLSearchParams(window.location.search);
      const token = params.get("t");

      if (token) {
        setState({ kind: "redeeming" });
        try {
          await redeemMagicLink(token);
          window.history.replaceState({}, "", "/chat");
        } catch (err) {
          if (cancelled) return;
          setState({
            kind: "error",
            message:
              err instanceof ApiError
                ? "This link is invalid or has already been used."
                : "Couldn't start your session.",
          });
          return;
        }
      }

      const me = await currentPatient();
      if (cancelled) return;
      if (me) {
        setState({ kind: "ready", patient: me });
      } else {
        setState({ kind: "needs_link" });
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-50">
      <CrisisBanner />
      <div className="mx-auto max-w-2xl px-4 py-8">
        {state.kind === "loading" || state.kind === "redeeming" ? (
          <p className="text-slate-600">Getting your chat ready…</p>
        ) : state.kind === "needs_link" ? (
          <NeedsLinkMessage />
        ) : state.kind === "error" ? (
          <p className="text-red-600">{state.message}</p>
        ) : (
          <ChatSurface patient={state.patient} />
        )}
      </div>
    </main>
  );
}

function NeedsLinkMessage() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">You&apos;ll need a new link</h1>
      <p className="mt-2 text-slate-600">
        Your therapist sends a one-time link to open this chat. Links expire
        after 15 minutes and can only be used once. Contact your therapist to
        request a fresh one.
      </p>
    </div>
  );
}

function CrisisBanner() {
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900">
      This chat is not a crisis service. If you&apos;re in danger, call or text{" "}
      <strong>988</strong> (US) or your local emergency number.
    </div>
  );
}
