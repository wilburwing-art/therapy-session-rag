// Server-side API client — forwards the therapist's cookie to the
// backend so server components can render authenticated data.

import { cookies, headers } from "next/headers";

export class ServerApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "ServerApiError";
  }
}

const BACKEND_URL = process.env.THERAPYRAG_API_URL ?? "http://localhost:8000";

export async function serverFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  const hs = await headers();

  const res = await fetch(`${BACKEND_URL}${path.startsWith("/") ? path : `/${path}`}`, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
      ...(hs.get("x-forwarded-for")
        ? { "x-forwarded-for": hs.get("x-forwarded-for") as string }
        : {}),
      ...(init.headers ?? {}),
    },
  });

  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");
  const body = isJson ? await res.json().catch(() => undefined) : await res.text();
  if (!res.ok) {
    const detail = isJson && body && typeof body === "object" && "detail" in body
      ? String((body as { detail?: unknown }).detail ?? res.statusText)
      : res.statusText;
    throw new ServerApiError(detail, res.status, body);
  }
  return body as T;
}

export async function serverFetchOrNull<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T | null> {
  try {
    return await serverFetch<T>(path, init);
  } catch (err) {
    if (err instanceof ServerApiError && (err.status === 401 || err.status === 404)) {
      return null;
    }
    throw err;
  }
}
