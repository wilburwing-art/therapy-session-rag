"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { RecordingUrlResponse, TranscriptSegment } from "@/lib/types";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; url: string }
  | { kind: "missing" }
  | { kind: "error"; message: string };

function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60)
    .toString()
    .padStart(2, "0");
  const s = (total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function findActiveSegmentIndex(
  segments: TranscriptSegment[],
  currentTime: number,
): number {
  if (segments.length === 0) return -1;
  // Primary pass: strict containment.
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (currentTime >= seg.start_time && currentTime < seg.end_time) {
      return i;
    }
  }
  // Fallback for gaps: last segment whose start_time <= currentTime.
  let idx = -1;
  for (let i = 0; i < segments.length; i++) {
    if (segments[i].start_time <= currentTime) {
      idx = i;
    } else {
      break;
    }
  }
  return idx;
}

export function SessionPlayer({
  sessionId,
  segments,
  fallbackText,
}: {
  sessionId: string;
  segments: TranscriptSegment[];
  fallbackText: string;
}) {
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const sortedSegments = useMemo(
    () => [...segments].sort((a, b) => a.start_time - b.start_time),
    [segments],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await apiFetch<RecordingUrlResponse>(
          `/v1/sessions/${sessionId}/recording/url`,
        );
        if (!cancelled) {
          setLoad({ kind: "ready", url: res.url });
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setLoad({ kind: "missing" });
          return;
        }
        setLoad({
          kind: "error",
          message:
            err instanceof ApiError ? err.message : "Could not load recording",
        });
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  function handleTimeUpdate() {
    const audio = audioRef.current;
    if (!audio) return;
    const idx = findActiveSegmentIndex(sortedSegments, audio.currentTime);
    setActiveIndex((prev) => (prev === idx ? prev : idx));
  }

  function handleSegmentClick(segment: TranscriptSegment) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = segment.start_time;
    void audio.play().catch(() => undefined);
  }

  function handleAudioError() {
    setLoad({
      kind: "error",
      message: "Recording unavailable",
    });
  }

  const unavailable =
    load.kind === "error" || load.kind === "missing";

  return (
    <div className="space-y-4">
      {load.kind === "loading" && (
        <p className="text-sm text-slate-500">Loading recording…</p>
      )}

      {load.kind === "ready" && (
        <audio
          ref={audioRef}
          controls
          src={load.url}
          onTimeUpdate={handleTimeUpdate}
          onError={handleAudioError}
          className="w-full"
        />
      )}

      {unavailable && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Recording unavailable
          {load.kind === "error" && load.message ? ` — ${load.message}` : ""}.
          Showing transcript text only.
        </div>
      )}

      {sortedSegments.length === 0 ? (
        <pre className="mt-2 max-h-[480px] overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-4 font-mono text-sm text-slate-800">
          {fallbackText}
        </pre>
      ) : unavailable ? (
        <pre className="mt-2 max-h-[480px] overflow-auto whitespace-pre-wrap rounded-md bg-slate-50 p-4 font-mono text-sm text-slate-800">
          {fallbackText}
        </pre>
      ) : (
        <ol className="max-h-[480px] space-y-2 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-2">
          {sortedSegments.map((seg, i) => {
            const active = i === activeIndex;
            return (
              <li key={`${seg.start_time}-${i}`}>
                <button
                  type="button"
                  data-active={active ? "true" : "false"}
                  aria-current={active ? "true" : undefined}
                  onClick={() => handleSegmentClick(seg)}
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                    active
                      ? "border-brand-500 bg-brand-50 text-brand-900"
                      : "border-transparent bg-white text-slate-800 hover:border-slate-300 hover:bg-slate-100"
                  }`}
                >
                  <span className="font-mono text-xs text-slate-500">
                    [{formatTimestamp(seg.start_time)}]
                  </span>{" "}
                  <span className="font-semibold text-slate-700">
                    {seg.speaker ?? "Speaker"}:
                  </span>{" "}
                  <span>{seg.text}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
