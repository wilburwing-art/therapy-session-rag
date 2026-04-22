import { serverFetch } from "@/lib/serverApi";
import { EventsTable } from "./EventsTable";

export type AuditEvent = {
  id: string;
  event_name: string;
  event_category: string;
  organization_id: string;
  actor_id: string | null;
  session_id: string | null;
  event_timestamp: string;
  properties: Record<string, unknown> | null;
};

export type EventsPage = {
  events: AuditEvent[];
  next_cursor: string | null;
  has_more: boolean;
};

export default async function AdminEventsPage({
  searchParams,
}: {
  searchParams: Promise<{
    category?: string;
    actor_id?: string;
    since?: string;
    until?: string;
    cursor?: string;
    limit?: string;
  }>;
}) {
  const params = await searchParams;
  const qs = new URLSearchParams();
  if (params.category) qs.set("category", params.category);
  if (params.actor_id) qs.set("actor_id", params.actor_id);
  if (params.since) qs.set("since", params.since);
  if (params.until) qs.set("until", params.until);
  if (params.cursor) qs.set("cursor", params.cursor);
  qs.set("limit", params.limit ?? "50");

  const page = await serverFetch<EventsPage>(
    `/api/v1/admin/events?${qs.toString()}`,
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold">Audit log</h1>
        <p className="mt-1 text-sm text-slate-600">
          Cross-tenant analytics events. Newest first.
        </p>
      </header>

      <EventsTable initial={page} initialFilters={params} />
    </div>
  );
}
