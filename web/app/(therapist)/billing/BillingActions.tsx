"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export function BillingActions({
  hasStripeCustomer,
}: {
  hasStripeCustomer: boolean;
}) {
  const [loading, setLoading] = useState<"checkout" | "portal" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function goCheckout() {
    setLoading("checkout");
    setError(null);
    try {
      const res = await apiFetch<{ url: string }>(
        "/v1/billing/checkout-session",
        { method: "POST" },
      );
      window.location.href = res.url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Checkout failed");
      setLoading(null);
    }
  }

  async function goPortal() {
    setLoading("portal");
    setError(null);
    try {
      const res = await apiFetch<{ url: string }>("/v1/billing/portal-session", {
        method: "POST",
      });
      window.location.href = res.url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open portal");
      setLoading(null);
    }
  }

  return (
    <div className="mt-6 flex flex-col gap-3 sm:flex-row">
      <button
        onClick={goCheckout}
        disabled={loading !== null}
        className="rounded-md bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700 disabled:opacity-50"
      >
        {loading === "checkout" ? "Opening…" : "Start or update subscription"}
      </button>
      {hasStripeCustomer && (
        <button
          onClick={goPortal}
          disabled={loading !== null}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading === "portal" ? "Opening…" : "Manage in Stripe"}
        </button>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
