// Fetch wrapper for the TherapyRAG backend.
//
// React Native's fetch does not persist cookies across requests (no
// shared cookie jar the way a browser has), so we pull the session
// cookie back out of expo-secure-store and inject it as a `Cookie`
// header ourselves.

import { getStoredSession } from "@/lib/secure_store";

export class ApiError extends Error {
  override readonly name = "ApiError";
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
  }
}

export interface ApiFetchOptions extends RequestInit {
  json?: unknown;
  /** If true, do not attach the session cookie (e.g., the redeem call). */
  skipAuth?: boolean;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function baseUrl(): string {
  const url = process.env.EXPO_PUBLIC_API_URL;
  if (!url) {
    throw new Error(
      "EXPO_PUBLIC_API_URL is not set. Define it in mobile/.env or your build config.",
    );
  }
  return url.replace(/\/$/, "");
}

/**
 * Parse `Set-Cookie` header values into a single `Cookie`-header
 * string. React Native's fetch returns `set-cookie` as a single
 * comma-joined string, but cookies themselves can contain commas
 * inside attribute values (e.g., Expires=Wed, 21 Oct…), so we split
 * on the `,` that precedes a `key=` pair rather than any comma.
 */
export function extractCookies(setCookie: string | null): Record<string, string> {
  if (!setCookie) return {};
  const parts = setCookie.split(/,(?=\s*[a-zA-Z0-9_\-]+=)/);
  const jar: Record<string, string> = {};
  for (const part of parts) {
    const firstSemi = part.indexOf(";");
    const pair = firstSemi === -1 ? part : part.slice(0, firstSemi);
    const eq = pair.indexOf("=");
    if (eq === -1) continue;
    const name = pair.slice(0, eq).trim();
    const value = pair.slice(eq + 1).trim();
    if (name) jar[name] = value;
  }
  return jar;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { json, headers, skipAuth, ...rest } = options;
  const method = (
    rest.method ?? (json !== undefined ? "POST" : "GET")
  ).toUpperCase();

  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (!skipAuth) {
    const session = await getStoredSession();
    if (session?.cookie) {
      baseHeaders["Cookie"] = session.cookie;
    }
    // Double-submit CSRF: the server reads therapyrag_csrf from the
    // Cookie header and expects X-CSRF-Token to echo its value on any
    // mutating request. Safe methods don't need it.
    if (!SAFE_METHODS.has(method) && session?.csrf) {
      baseHeaders["X-CSRF-Token"] = session.csrf;
    }
  }

  const init: RequestInit = {
    ...rest,
    method,
    headers: {
      ...baseHeaders,
      ...((headers as Record<string, string> | undefined) ?? {}),
    },
  };

  if (json !== undefined) {
    init.body = JSON.stringify(json);
  }

  const url = `${baseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, init);
  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const body: unknown = isJson
    ? await res.json().catch(() => undefined)
    : await res.text().catch(() => "");

  if (!res.ok) {
    const detail =
      isJson && body && typeof body === "object" && "detail" in body
        ? String((body as { detail?: unknown }).detail ?? res.statusText)
        : res.statusText;
    throw new ApiError(detail, res.status, body);
  }

  return body as T;
}

/**
 * Same as apiFetch but also exposes the raw Response so callers
 * (namely the magic-link redeem flow) can read the `Set-Cookie`
 * header to build the persisted session.
 */
export async function apiFetchRaw(
  path: string,
  options: ApiFetchOptions = {},
): Promise<{ res: Response; body: unknown }> {
  const { json, headers, skipAuth, ...rest } = options;
  const method = (
    rest.method ?? (json !== undefined ? "POST" : "GET")
  ).toUpperCase();

  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (!skipAuth) {
    const session = await getStoredSession();
    if (session?.cookie) baseHeaders["Cookie"] = session.cookie;
    if (!SAFE_METHODS.has(method) && session?.csrf) {
      baseHeaders["X-CSRF-Token"] = session.csrf;
    }
  }

  const init: RequestInit = {
    ...rest,
    method,
    headers: {
      ...baseHeaders,
      ...((headers as Record<string, string> | undefined) ?? {}),
    },
  };
  if (json !== undefined) init.body = JSON.stringify(json);

  const url = `${baseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, init);
  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const body: unknown = isJson
    ? await res.json().catch(() => undefined)
    : await res.text().catch(() => "");

  if (!res.ok) {
    const detail =
      isJson && body && typeof body === "object" && "detail" in body
        ? String((body as { detail?: unknown }).detail ?? res.statusText)
        : res.statusText;
    throw new ApiError(detail, res.status, body);
  }

  return { res, body };
}
