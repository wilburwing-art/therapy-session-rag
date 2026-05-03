import type { Page } from "@playwright/test";

export type TherapistCredentials = {
  email: string;
  password: string;
  fullName: string;
  practiceName: string;
};

export function uniqueTherapist(tag = "e2e"): TherapistCredentials {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1_000)}`;
  return {
    email: `dr-${tag}-${stamp}@example.test`,
    password: "correct-horse-battery-staple",
    fullName: "Dr Test Therapist",
    practiceName: `Test Practice ${stamp}`,
  };
}

export function uniquePatientEmail(tag = "pt"): string {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1_000)}`;
  return `patient-${tag}-${stamp}@example.test`;
}

// Fills and submits the signup form. Leaves the browser wherever
// the app lands after registration (currently /billing?new=true).
export async function signUpTherapist(
  page: Page,
  creds: TherapistCredentials,
): Promise<void> {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill(creds.fullName);
  await page.getByLabel("Practice name").fill(creds.practiceName);
  await page.getByLabel("Work email").fill(creds.email);
  await page.getByLabel("Password (min 8 chars)").fill(creds.password);
  await page.getByRole("button", { name: /create account/i }).click();
  // Signup redirects to /billing?new=true on success.
  await page.waitForURL(/\/billing/);
}

// Fills and submits the login form. Waits for /dashboard to load.
export async function signInTherapist(
  page: Page,
  creds: Pick<TherapistCredentials, "email" | "password">,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(creds.email);
  await page.getByLabel("Password").fill(creds.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/);
}

// Performs a sign-out via the header form (POST /logout).
export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: /log out/i }).click();
  await page.waitForURL(/\/login/);
}
