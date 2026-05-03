"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { AuditEvent, EventsPage } from "./page";

const CATEGORIES = ["", "user_action", "system", "clinical", "performance"];

export function EventsTable({
  initial,
  initialFilters,
}: {
  initial: EventsPage;
  initialFilters: {
    category?: string;
    actor_id?: string;
    since?: string;
    until?: string;
  };
}) {
  const router = useRouter();
  const [category, setCategory] = useState(initialFilters.category ?? "");
  const [actorId, setActorId] = useState(initialFilters.actor_id ?? "");
  const [since, setSince] = useState(initialFilters.since ?? "");
  const [until, setUntil] = useState(initialFilters.until ?? "");

  function applyFilters(extra?: { cursor?: string }) {
    const qs = new URLSearchParams();
    if (category) qs.set("category", category);
    if (actorId) qs.set("actor_id", actorId);
    if (since) qs.set("since", since);
    if (until) qs.set("until", until);
    if (extra?.cursor) qs.set("cursor", extra.cursor);
    router.push(`/admin/events?${qs.toString()}`);
  }

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          applyFilters();
        }}
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      >
        <div className="grid gap-3 md:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-slate-600">Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c || "Any"}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-slate-600">Actor ID</span>
            <input
              type="text"
              value={actorId}
              onChange={(e) => setActorId(e.target.value)}
              placeholder="UUID"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-slate-600">Since</span>
            <input
              type="datetime-local"
              value={since}
              onChange={(e) => setSince(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-slate-600">Until</span>
            <input
              type="datetime-local"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="submit"
            className="rounded-md bg-brand-600 px-4 py-1.5 text-sm text-white hover:bg-brand-700"
          >
            Apply filters
          </button>
          <button
            type="button"
            onClick={() => {
              setCategory("");
              setActorId("");
              setSince("");
              setUntil("");
              router.push("/admin/events");
            }}
            className="rounded-md border border-slate-300 bg-white px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Clear
          </button>
        </div>
      </form>

      {initial.events.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600">
          No events for the current filters.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Org</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Properties</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {initial.events.map((e) => (
                <EventRow key={e.id} event={e} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {initial.has_more && initial.next_cursor && (
        <div className="flex justify-end">
          <button
            onClick={() =>
              applyFilters({ cursor: initial.next_cursor ?? undefined })
            }
            className="rounded-md border border-slate-300 bg-white px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Next page →
          </button>
        </div>
      )}
    </div>
  );
}

function EventRow({ event }: { event: AuditEvent }) {
  return (
    <tr className="hover:bg-slate-50 align-top">
      <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-600">
        {new Date(event.event_timestamp).toLocaleString()}
      </td>
      <td className="px-4 py-3 font-medium text-slate-900">
        {event.event_name}
      </td>
      <td className="px-4 py-3 text-xs uppercase tracking-wide text-slate-500">
        {event.event_category}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-slate-600">
        {event.organization_id.slice(0, 8)}…
      </td>
      <td className="px-4 py-3 font-mono text-xs text-slate-600">
        {event.actor_id ? `${event.actor_id.slice(0, 8)}…` : "—"}
      </td>
      <td className="px-4 py-3">
        {event.properties ? (
          <pre className="max-w-md overflow-x-auto rounded bg-slate-100 p-2 text-xs text-slate-700">
            {JSON.stringify(event.properties, null, 2)}
          </pre>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </td>
    </tr>
  );
}
