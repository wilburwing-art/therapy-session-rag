import Link from "next/link";
import { serverFetch } from "@/lib/serverApi";
import type { ConversationRead } from "@/lib/types";

export default async function ConversationReviewPage({
  params,
}: {
  params: Promise<{ id: string; conversationId: string }>;
}) {
  const { id, conversationId } = await params;
  const conversation = await serverFetch<ConversationRead>(
    `/api/v1/patients/${id}/conversations/${conversationId}`,
  );

  return (
    <div className="space-y-6">
      <Link
        href={`/patients/${id}`}
        className="text-sm text-brand-700 hover:underline"
      >
        ← Back to patient
      </Link>
      <h1 className="text-2xl font-semibold">
        {conversation.title ?? "Patient chatbot conversation"}
      </h1>
      <div className="space-y-4">
        {conversation.messages.map((m) => (
          <div
            key={m.id}
            className={`rounded-xl border border-slate-200 p-4 ${m.role === "user" ? "bg-white" : "bg-brand-50"}`}
          >
            <p className="text-xs uppercase tracking-wide text-slate-500">
              {m.role === "user" ? "Patient" : "Assistant"} ·{" "}
              {new Date(m.created_at).toLocaleString()}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-slate-800">
              {m.content}
            </p>
            {m.sources && m.sources.length > 0 && (
              <div className="mt-3 space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-600">
                <p className="font-medium">Sources:</p>
                <ul className="space-y-1">
                  {m.sources.map((s) => (
                    <li key={s.chunk_id}>
                      {s.start_time != null
                        ? `@${Math.round(s.start_time)}s · `
                        : ""}
                      {s.content_preview.slice(0, 120)}…
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
