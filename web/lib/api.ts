// Thin wrapper around fetch for calling the TherapyRAG backend.
// Requests go through Next.js rewrites at `/api/*` so cookies are
// same-origin and no CORS is needed in production.

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ApiFetchOptions = RequestInit & {
  json?: unknown;
};

const CSRF_COOKIE = "therapyrag_csrf";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  for (const part of document.cookie.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (rawKey === CSRF_COOKIE && rest.length > 0) {
      return decodeURIComponent(rest.join("="));
    }
  }
  return null;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { json, headers, ...rest } = options;
  const method = (rest.method ?? (json !== undefined ? "POST" : "GET")).toUpperCase();

  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  // Double-submit CSRF: echo the server-set cookie back in a header on
  // every state-changing request. Safe methods don't need it.
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCsrfCookie();
    if (csrf) baseHeaders["X-CSRF-Token"] = csrf;
  }

  const init: RequestInit = {
    credentials: "include",
    ...rest,
    method,
    headers: {
      ...baseHeaders,
      ...(headers ?? {}),
    },
  };

  if (json !== undefined) {
    init.body = JSON.stringify(json);
  }

  const res = await fetch(`/api${path.startsWith("/") ? path : `/${path}`}`, init);
  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");
  const body = isJson ? await res.json().catch(() => undefined) : await res.text();

  if (!res.ok) {
    const detail = isJson && body && typeof body === "object" && "detail" in body
      ? String((body as { detail?: unknown }).detail ?? res.statusText)
      : res.statusText;
    throw new ApiError(detail, res.status, body);
  }

  return body as T;
}
