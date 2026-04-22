import { expect, test } from "@playwright/test";
import {
  signInTherapist,
  signOut,
  signUpTherapist,
  uniqueTherapist,
} from "./fixtures/accounts";

test.describe("signup and login", () => {
  test("therapist can register, log out, and log back in", async ({ page }) => {
    const creds = uniqueTherapist();

    await signUpTherapist(page, creds);

    // Post-signup lands on billing. Go to the dashboard explicitly to
    // verify the new account has a usable session.
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();

    await signOut(page);
    await expect(page).toHaveURL(/\/login/);

    await signInTherapist(page, creds);
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  });
});
