import { apiFetch, ApiError } from "./api";
import type { CurrentPatient, CurrentUser, LoginResponse } from "./types";

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/v1/auth/login", {
    json: { email, password },
  });
}

export async function register(input: {
  email: string;
  password: string;
  full_name: string;
  practice_name: string;
}) {
  return apiFetch("/v1/auth/register", { json: input });
}

export async function logout(): Promise<void> {
  await apiFetch("/v1/auth/logout", { method: "POST" });
}

export async function me(): Promise<CurrentUser | null> {
  try {
    return await apiFetch<CurrentUser>("/v1/auth/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

export async function redeemMagicLink(token: string) {
  return apiFetch<{
    patient_id: string;
    organization_id: string;
    expires_at: string;
  }>("/v1/auth/patient/session", { json: { token } });
}

export async function currentPatient(): Promise<CurrentPatient | null> {
  try {
    return await apiFetch<CurrentPatient>("/v1/auth/patient/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}
