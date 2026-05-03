import { serverFetch } from "@/lib/serverApi";
import type { HomeworkItemRecord } from "@/lib/types";

/**
 * Therapist-side read-only summary of a patient's homework items.
 * Patient-dashboard-engineer owns the patient-facing write surface.
 */
export async function HomeworkSection({ patientId }: { patientId: string }) {
  const items = await serverFetch<HomeworkItemRecord[]>(
    `/api/v1/patients/${patientId}/homework?limit=50`,
  ).catch(() => [] as HomeworkItemRecord[]);

  const open = items.filter((i) => !i.completed);
  const done = items.filter((i) => i.completed);

  return (
    <section>
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Homework</h2>
        <span className="text-sm text-slate-500">
          {open.length} open · {done.length} completed
        </span>
      </div>
      {items.length === 0 ? (
        <p className="mt-4 text-slate-600">
          No homework recorded yet. Items appear once session recaps are
          generated.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {open.length > 0 && (
            <HomeworkList title="Open" items={open} />
          )}
          {done.length > 0 && (
            <HomeworkList title="Completed" items={done} muted />
          )}
        </div>
      )}
    </section>
  );
}

function HomeworkList({
  title,
  items,
  muted = false,
}: {
  title: string;
  items: HomeworkItemRecord[];
  muted?: boolean;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      <ul className="mt-2 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white">
        {items.map((item) => (
          <li
            key={item.id}
            className={`px-4 py-3 ${muted ? "text-slate-500" : "text-slate-800"}`}
          >
            <p className={muted ? "line-through" : "font-medium"}>{item.task}</p>
            {item.notes && (
              <p className="mt-1 text-sm text-slate-500">{item.notes}</p>
            )}
            {item.completed && item.completed_at && (
              <p className="mt-1 text-xs text-slate-400">
                Completed {new Date(item.completed_at).toLocaleDateString()}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
