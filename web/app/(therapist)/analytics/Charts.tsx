"use client";

import { useMemo, useState } from "react";

// -----------------------------------------------------------------------------
// API response types (kept local so the server page can import them too)
// -----------------------------------------------------------------------------

export type SessionsByWeekPoint = {
  week_start: string; // ISO date
  count: number;
};

export type SessionsByStatusResponse = {
  counts: Record<string, number>;
};

export type ActivePatientsResponse = {
  window_days: number;
  active_patients: number;
};

export type ChatActivityPoint = {
  day: string; // ISO date
  message_count: number;
};

export type AssessmentTrendPoint = {
  week_start: string; // ISO date
  avg_score: number | null;
  count: number;
};

export type AssessmentTrendResponse = {
  instrument: "phq9" | "gad7";
  points: AssessmentTrendPoint[];
};

// -----------------------------------------------------------------------------
// Status color map (Tailwind classes).
// -----------------------------------------------------------------------------

const STATUS_COLORS: Record<string, { fill: string; bg: string; text: string }> =
  {
    ready: { fill: "fill-emerald-500", bg: "bg-emerald-500", text: "text-emerald-900" },
    uploaded: { fill: "fill-blue-400", bg: "bg-blue-400", text: "text-blue-900" },
    transcribing: { fill: "fill-indigo-400", bg: "bg-indigo-400", text: "text-indigo-900" },
    embedding: { fill: "fill-violet-400", bg: "bg-violet-400", text: "text-violet-900" },
    pending: { fill: "fill-slate-300", bg: "bg-slate-300", text: "text-slate-800" },
    failed: { fill: "fill-red-500", bg: "bg-red-500", text: "text-red-900" },
  };

function statusColor(status: string) {
  return (
    STATUS_COLORS[status] ?? {
      fill: "fill-slate-400",
      bg: "bg-slate-400",
      text: "text-slate-900",
    }
  );
}

// -----------------------------------------------------------------------------
// Clinical cutpoints for PHQ-9 / GAD-7 severity bands.
// Mirrors the backend scoring in src/services/assessment_service.py.
// -----------------------------------------------------------------------------

type SeverityBand = {
  label: string;
  min: number;
  max: number;
  fill: string; // SVG fill class
};

const PHQ9_BANDS: SeverityBand[] = [
  { label: "minimal", min: 0, max: 4, fill: "fill-emerald-100" },
  { label: "mild", min: 5, max: 9, fill: "fill-lime-100" },
  { label: "moderate", min: 10, max: 14, fill: "fill-amber-100" },
  { label: "moderately severe", min: 15, max: 19, fill: "fill-orange-100" },
  { label: "severe", min: 20, max: 27, fill: "fill-red-100" },
];

const GAD7_BANDS: SeverityBand[] = [
  { label: "minimal", min: 0, max: 4, fill: "fill-emerald-100" },
  { label: "mild", min: 5, max: 9, fill: "fill-lime-100" },
  { label: "moderate", min: 10, max: 14, fill: "fill-amber-100" },
  { label: "severe", min: 15, max: 21, fill: "fill-red-100" },
];

const PHQ9_MAX = 27;
const GAD7_MAX = 21;

// -----------------------------------------------------------------------------
// Formatting helpers
// -----------------------------------------------------------------------------

function formatShortDate(iso: string): string {
  // ISO date string like "2026-02-03" renders as "Feb 3".
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

// -----------------------------------------------------------------------------
// Reusable primitives
// -----------------------------------------------------------------------------

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-4xl font-semibold text-slate-900">{value}</p>
      {sub && <p className="mt-1 text-sm text-slate-500">{sub}</p>}
    </div>
  );
}

type BarChartProps<T> = {
  data: T[];
  labelFor: (d: T) => string;
  valueFor: (d: T) => number;
  height?: number;
  ariaLabel?: string;
};

export function BarChart<T>({
  data,
  labelFor,
  valueFor,
  height = 180,
  ariaLabel,
}: BarChartProps<T>) {
  const padding = { top: 10, right: 8, bottom: 28, left: 32 };
  const innerH = height - padding.top - padding.bottom;
  // Treat the chart area as a 320-unit wide viewBox and let CSS scale it.
  const innerW = 320;
  const width = innerW + padding.left + padding.right;

  const values = data.map(valueFor);
  const maxValue = Math.max(1, ...values);
  const barGap = 4;
  const barWidth =
    data.length > 0 ? (innerW - barGap * (data.length - 1)) / data.length : 0;

  // Five evenly spaced gridlines.
  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      role="img"
      aria-label={ariaLabel}
    >
      {/* Grid + Y-axis ticks */}
      {gridLines.map((frac) => {
        const y = padding.top + innerH * (1 - frac);
        const value = Math.round(maxValue * frac);
        return (
          <g key={frac}>
            <line
              x1={padding.left}
              x2={padding.left + innerW}
              y1={y}
              y2={y}
              className="stroke-slate-200"
              strokeWidth={1}
            />
            <text
              x={padding.left - 4}
              y={y + 3}
              textAnchor="end"
              className="fill-slate-500 text-[9px]"
            >
              {value}
            </text>
          </g>
        );
      })}

      {/* Bars */}
      {data.map((d, i) => {
        const v = valueFor(d);
        const barH = maxValue > 0 ? (v / maxValue) * innerH : 0;
        const x = padding.left + i * (barWidth + barGap);
        const y = padding.top + innerH - barH;
        return (
          <g key={i}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={barH}
              rx={2}
              className="fill-brand-500 hover:fill-brand-700"
            >
              <title>{`${labelFor(d)}: ${v}`}</title>
            </rect>
            {/* X-axis label every other bar to avoid crowding. */}
            {(i === 0 || i === data.length - 1 || i % 2 === 1) && (
              <text
                x={x + barWidth / 2}
                y={height - 8}
                textAnchor="middle"
                className="fill-slate-500 text-[9px]"
              >
                {labelFor(d)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

type LineChartProps<T> = {
  data: T[];
  labelFor: (d: T) => string;
  valueFor: (d: T) => number | null;
  height?: number;
  maxOverride?: number;
  bands?: SeverityBand[]; // Optional shaded severity bands for score charts.
  ariaLabel?: string;
};

export function LineChart<T>({
  data,
  labelFor,
  valueFor,
  height = 200,
  maxOverride,
  bands,
  ariaLabel,
}: LineChartProps<T>) {
  const padding = { top: 12, right: 12, bottom: 28, left: 32 };
  const innerW = 360;
  const innerH = height - padding.top - padding.bottom;
  const width = innerW + padding.left + padding.right;

  const numericValues = data
    .map(valueFor)
    .filter((v): v is number => v !== null);
  const rawMax = Math.max(1, ...numericValues);
  const maxValue = maxOverride ?? rawMax;

  const stepX = data.length > 1 ? innerW / (data.length - 1) : innerW;
  const points = data.map((d, i) => {
    const v = valueFor(d);
    if (v === null) return null;
    const x = padding.left + i * stepX;
    const y = padding.top + innerH - (v / maxValue) * innerH;
    return { x, y, v, label: labelFor(d) };
  });

  const pathD = points
    .map((p, i) => {
      if (p === null) return "";
      return `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`;
    })
    .filter(Boolean)
    .join(" ");

  // Y-axis labels: 0, 25%, 50%, 75%, 100% of maxValue.
  const yTicks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full"
      role="img"
      aria-label={ariaLabel}
    >
      {/* Severity bands (drawn behind gridlines) */}
      {bands?.map((band) => {
        const yTop =
          padding.top + innerH - Math.min(1, band.max / maxValue) * innerH;
        const yBottom =
          padding.top + innerH - Math.min(1, band.min / maxValue) * innerH;
        const bandH = yBottom - yTop;
        return (
          <rect
            key={band.label}
            x={padding.left}
            y={yTop}
            width={innerW}
            height={bandH}
            className={band.fill}
            opacity={0.6}
          >
            <title>{`${band.label} (${band.min}-${band.max})`}</title>
          </rect>
        );
      })}

      {/* Gridlines + Y ticks */}
      {yTicks.map((frac) => {
        const y = padding.top + innerH * (1 - frac);
        const value = Math.round(maxValue * frac);
        return (
          <g key={frac}>
            <line
              x1={padding.left}
              x2={padding.left + innerW}
              y1={y}
              y2={y}
              className="stroke-slate-200"
              strokeWidth={1}
            />
            <text
              x={padding.left - 4}
              y={y + 3}
              textAnchor="end"
              className="fill-slate-500 text-[9px]"
            >
              {value}
            </text>
          </g>
        );
      })}

      {/* Line */}
      {pathD && (
        <path
          d={pathD}
          className="fill-none stroke-brand-600"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {/* Points with tooltips */}
      {points.map((p, i) =>
        p === null ? null : (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={3} className="fill-brand-700">
              <title>{`${p.label}: ${p.v}`}</title>
            </circle>
          </g>
        ),
      )}

      {/* First / last X labels */}
      {data.length > 0 && (
        <>
          <text
            x={padding.left}
            y={height - 8}
            textAnchor="start"
            className="fill-slate-500 text-[9px]"
          >
            {labelFor(data[0])}
          </text>
          <text
            x={padding.left + innerW}
            y={height - 8}
            textAnchor="end"
            className="fill-slate-500 text-[9px]"
          >
            {labelFor(data[data.length - 1])}
          </text>
        </>
      )}
    </svg>
  );
}

// -----------------------------------------------------------------------------
// Sessions-by-status horizontal stacked bar
// -----------------------------------------------------------------------------

function StatusStackedBar({ counts }: { counts: Record<string, number> }) {
  const entries = useMemo(
    () => Object.entries(counts).filter(([, v]) => v > 0),
    [counts],
  );
  const total = entries.reduce((acc, [, v]) => acc + v, 0);

  if (total === 0) {
    return (
      <p className="text-sm text-slate-500">
        No sessions yet.
      </p>
    );
  }

  return (
    <div>
      <div className="flex h-6 w-full overflow-hidden rounded-md border border-slate-200">
        {entries.map(([status, count]) => {
          const pct = (count / total) * 100;
          const color = statusColor(status);
          return (
            <div
              key={status}
              className={color.bg}
              style={{ width: `${pct}%` }}
              title={`${status}: ${count}`}
            />
          );
        })}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        {entries.map(([status, count]) => {
          const color = statusColor(status);
          return (
            <li key={status} className="flex items-center gap-2">
              <span
                aria-hidden
                className={`inline-block h-2.5 w-2.5 rounded-sm ${color.bg}`}
              />
              <span className="capitalize text-slate-700">{status}</span>
              <span className="ml-auto font-medium text-slate-900">
                {count}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Top-level component
// -----------------------------------------------------------------------------

type ChartsProps = {
  sessionsByWeek: SessionsByWeekPoint[];
  sessionsByStatus: SessionsByStatusResponse;
  activePatients: ActivePatientsResponse;
  chatActivity: ChatActivityPoint[];
  phq9Trend: AssessmentTrendResponse;
  gad7Trend: AssessmentTrendResponse;
};

export function Charts({
  sessionsByWeek,
  sessionsByStatus,
  activePatients,
  chatActivity,
  phq9Trend,
  gad7Trend,
}: ChartsProps) {
  const [assessmentView, setAssessmentView] = useState<"phq9" | "gad7">("phq9");

  const sessionsThisWeek = sessionsByWeek.length
    ? sessionsByWeek[sessionsByWeek.length - 1].count
    : 0;
  const totalSessions = sessionsByWeek.reduce((acc, p) => acc + p.count, 0);

  const activeTrend = assessmentView === "phq9" ? phq9Trend : gad7Trend;
  const activeBands = assessmentView === "phq9" ? PHQ9_BANDS : GAD7_BANDS;
  const activeMax = assessmentView === "phq9" ? PHQ9_MAX : GAD7_MAX;

  return (
    <div className="space-y-8">
      {/* Top-row stat cards */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Active patients"
          value={activePatients.active_patients}
          sub={`in the last ${activePatients.window_days} days`}
        />
        <StatCard
          label="Sessions this week"
          value={sessionsThisWeek}
          sub={`${totalSessions} in the last ${sessionsByWeek.length} weeks`}
        />
        <StatCard
          label="Chat messages (30d)"
          value={chatActivity.reduce((acc, p) => acc + p.message_count, 0)}
          sub="across all patients"
        />
      </section>

      {/* Sessions by week */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <header className="mb-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Sessions by week
          </h2>
          <p className="text-sm text-slate-500">
            Session volume over the last {sessionsByWeek.length} weeks.
          </p>
        </header>
        <div className="h-48">
          <BarChart
            data={sessionsByWeek}
            labelFor={(d) => formatShortDate(d.week_start)}
            valueFor={(d) => d.count}
            ariaLabel="Sessions per week"
          />
        </div>
      </section>

      {/* Sessions by status */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <header className="mb-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Sessions by status
          </h2>
          <p className="text-sm text-slate-500">
            Distribution of processing state across every session.
          </p>
        </header>
        <StatusStackedBar counts={sessionsByStatus.counts} />
      </section>

      {/* Chat activity */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <header className="mb-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Chat activity
          </h2>
          <p className="text-sm text-slate-500">
            Daily patient chatbot messages over the last {chatActivity.length}{" "}
            days.
          </p>
        </header>
        <div className="h-52">
          <LineChart
            data={chatActivity}
            labelFor={(d) => formatShortDate(d.day)}
            valueFor={(d) => d.message_count}
            ariaLabel="Chat messages per day"
          />
        </div>
      </section>

      {/* Assessment trend */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Assessment score trend
            </h2>
            <p className="text-sm text-slate-500">
              Weekly average, with clinical severity bands shaded.
            </p>
          </div>
          <div className="inline-flex rounded-md border border-slate-200 bg-white text-sm">
            <button
              type="button"
              onClick={() => setAssessmentView("phq9")}
              className={
                "px-3 py-1.5 " +
                (assessmentView === "phq9"
                  ? "bg-brand-600 text-white"
                  : "text-slate-600 hover:bg-slate-50")
              }
            >
              PHQ-9
            </button>
            <button
              type="button"
              onClick={() => setAssessmentView("gad7")}
              className={
                "px-3 py-1.5 " +
                (assessmentView === "gad7"
                  ? "bg-brand-600 text-white"
                  : "text-slate-600 hover:bg-slate-50")
              }
            >
              GAD-7
            </button>
          </div>
        </header>
        <div className="h-60">
          <LineChart
            data={activeTrend.points}
            labelFor={(d) => formatShortDate(d.week_start)}
            valueFor={(d) => d.avg_score}
            bands={activeBands}
            maxOverride={activeMax}
            ariaLabel={`${assessmentView.toUpperCase()} weekly average`}
          />
        </div>
        <ul className="mt-3 flex flex-wrap gap-3 text-xs text-slate-600">
          {activeBands.map((band) => (
            <li key={band.label} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className={
                  "inline-block h-2.5 w-2.5 rounded-sm " +
                  band.fill.replace("fill-", "bg-")
                }
              />
              <span className="capitalize">
                {band.label} ({band.min}-{band.max})
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
