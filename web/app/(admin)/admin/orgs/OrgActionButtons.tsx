"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

export function OrgActionButtons({
  orgId,
  disabled,
}: {
  orgId: string;
  disabled: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setPending(true);
    setError(null);
    try {
      const path = disabled
        ? `/v1/admin/orgs/${orgId}/enable`
        : `/v1/admin/orgs/${orgId}/disable`;
      await apiFetch(path, { method: "POST" });
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <button
        onClick={toggle}
        disabled={pending}
        className={
          disabled
            ? "rounded-md bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
            : "rounded-md bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-700 disabled:opacity-50"
        }
      >
        {pending ? "…" : disabled ? "Enable" : "Disable"}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
