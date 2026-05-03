"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type SearchSource = "transcript" | "recap" | "notes";

type SearchHit = {
  session_id: string;
  patient_id: string;
  patient_name: string | null;
  session_date: string;
  source: SearchSource;
  snippet: string;
  rank: number;
};

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

const SOURCE_LABEL: Record<SearchSource, string> = {
  transcript: "Transcript",
  recap: "Recap",
  notes: "Notes",
};

const SOURCE_BADGE_CLASS: Record<SearchSource, string> = {
  transcript: "bg-blue-100 text-blue-800",
  recap: "bg-amber-100 text-amber-800",
  notes: "bg-violet-100 text-violet-800",
};

// Allowlist sanitizer: escape everything and then re-inject only <mark> and
// </mark>. This keeps us safe against arbitrary HTML injected via the
// snippet text while still letting the highlight tags through.
function renderSnippet(raw: string): string {
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
  return escaped
    .replace(/&lt;mark&gt;/g, "<mark>")
    .replace(/&lt;\/mark&gt;/g, "</mark>");
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function SearchForm() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    if (debounced.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    apiFetch<SearchHit[]>(
      `/v1/search?q=${encodeURIComponent(debounced)}`,
    )
      .then((hits) => {
        if (cancelled) return;
        setResults(hits);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Search failed");
        }
        setResults([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const showEmpty = useMemo(
    () =>
      !loading &&
      !error &&
      debounced.length >= MIN_QUERY_LENGTH &&
      results.length === 0,
    [loading, error, debounced, results.length],
  );

  return (
    <div className="space-y-4">
      <label className="block">
        <span className="sr-only">Search query</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search transcripts, recaps, and notes…"
          className="w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 sm:text-sm"
          aria-label="Search query"
        />
      </label>

      {loading && <p className="text-sm text-slate-500">Searching…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {showEmpty && (
        <p className="text-sm text-slate-500">
          No matches for &ldquo;{debounced}&rdquo;.
        </p>
      )}

      {results.length > 0 && (
        <ul className="space-y-3">
          {results.map((hit) => (
            <li
              key={`${hit.session_id}-${hit.source}`}
              className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <Link
                    href={`/patients/${hit.patient_id}`}
                    className="text-sm font-medium text-brand-700 hover:underline"
                  >
                    {hit.patient_name ?? "Unnamed patient"}
                  </Link>
                  <Link
                    href={`/sessions/${hit.session_id}`}
                    className="block text-xs text-slate-500 hover:text-slate-700"
                  >
                    {formatDate(hit.session_date)}
                  </Link>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${SOURCE_BADGE_CLASS[hit.source]}`}
                >
                  {SOURCE_LABEL[hit.source]}
                </span>
              </div>
              <p
                className="mt-2 text-sm text-slate-700"
                // Snippet is sanitized via renderSnippet() above; we
                // deliberately opt into dangerouslySetInnerHTML to keep
                // <mark> highlights from ts_headline.
                dangerouslySetInnerHTML={{ __html: renderSnippet(hit.snippet) }}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
