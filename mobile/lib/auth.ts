// Patient auth flow: redeem a magic-link token, persist the resulting
// session cookie in expo-secure-store, hydrate on app launch.

import {
  apiFetch,
  apiFetchRaw,
  ApiError,
  extractCookies,
} from "@/lib/api";
import {
  clearStoredSession,
  getStoredSession,
  setStoredSession,
} from "@/lib/secure_store";
import type {
  CurrentPatient,
  MagicLinkRedeemResponse,
  StoredSession,
} from "@/types";

const PATIENT_COOKIE = "therapyrag_patient";
const CSRF_COOKIE = "therapyrag_csrf";

/**
 * POST /auth/patient/session with the one-time magic-link token.
 * On success, pulls the session + CSRF cookie out of the response's
 * Set-Cookie header and persists them in expo-secure-store.
 */
export async function redeemMagicLink(
  token: string,
): Promise<StoredSession> {
  const { res, body } = await apiFetchRaw("/api/v1/auth/patient/session", {
    method: "POST",
    json: { token },
    skipAuth: true,
  });

  const redeem = body as MagicLinkRedeemResponse;
  const setCookie = res.headers.get("set-cookie");
  const jar = extractCookies(setCookie);
  const sessionValue = jar[PATIENT_COOKIE];
  if (!sessionValue) {
    throw new ApiError(
      "Server did not return a patient session cookie",
      500,
      { setCookie },
    );
  }

  // Cookie header the server will re-recognize on subsequent requests.
  const cookieParts = [`${PATIENT_COOKIE}=${sessionValue}`];
  const csrf = jar[CSRF_COOKIE] ?? null;
  if (csrf) cookieParts.push(`${CSRF_COOKIE}=${csrf}`);
  const cookieHeader = cookieParts.join("; ");

  const stored: StoredSession = {
    cookie: cookieHeader,
    patient_id: redeem.patient_id,
    organization_id: redeem.organization_id,
    expires_at: redeem.expires_at,
    csrf,
  };
  await setStoredSession(stored);
  return stored;
}

/** Read the persisted session from expo-secure-store (no network). */
export async function getSession(): Promise<StoredSession | null> {
  const stored = await getStoredSession();
  if (!stored) return null;
  if (isExpired(stored.expires_at)) {
    await clearStoredSession();
    return null;
  }
  return stored;
}

export async function clearSession(): Promise<void> {
  try {
    // Best-effort server-side invalidation; we still drop local state
    // even if it fails (e.g., offline or token already expired).
    await apiFetch("/api/v1/auth/patient/logout", { method: "POST" });
  } catch {
    // Fall through to local clear.
  }
  await clearStoredSession();
}

/** Hit /auth/patient/me to confirm the stored cookie still works. */
export async function fetchCurrentPatient(): Promise<CurrentPatient | null> {
  try {
    return await apiFetch<CurrentPatient>("/api/v1/auth/patient/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      await clearStoredSession();
      return null;
    }
    throw err;
  }
}

function isExpired(iso: string): boolean {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return false;
  return t <= Date.now();
}
