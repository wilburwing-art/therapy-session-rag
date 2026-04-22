import { expect, test } from "@playwright/test";
import {
  signUpTherapist,
  uniqueTherapist,
} from "./fixtures/accounts";

test.describe("invite therapist", () => {
  test("owner invites a colleague; colleague accepts and both appear in the team list", async ({
    browser,
  }) => {
    const owner = uniqueTherapist("owner");
    const colleague = uniqueTherapist("colleague");

    // ---- Context A: the owner signs up and invites the colleague ----
    const ownerContext = await browser.newContext();
    const ownerPage = await ownerContext.newPage();

    await signUpTherapist(ownerPage, owner);

    // Capture the invite token from the backend response so we don't
    // have to rely on the UI truncating long URLs.
    const inviteResponsePromise = ownerPage.waitForResponse(
      (res) =>
        res.url().endsWith("/api/v1/invites") &&
        res.request().method() === "POST" &&
        res.ok(),
    );

    await ownerPage.goto("/settings/team");
    await expect(
      ownerPage.getByRole("heading", { name: "Team" }),
    ).toBeVisible();

    await ownerPage
      .getByPlaceholder("colleague@example.com")
      .fill(colleague.email);
    await ownerPage.getByRole("button", { name: /send invite/i }).click();

    const inviteResponse = await inviteResponsePromise;
    const invite = (await inviteResponse.json()) as {
      token: string;
      email: string;
    };
    expect(invite.email).toBe(colleague.email);
    expect(invite.token).toBeTruthy();

    // UI confirms success.
    await expect(ownerPage.getByText(/invite sent to/i)).toBeVisible();
    await expect(
      ownerPage.getByText(colleague.email).first(),
    ).toBeVisible();

    // ---- Context B: the colleague accepts the invite ----
    const colleagueContext = await browser.newContext();
    const colleaguePage = await colleagueContext.newPage();

    await colleaguePage.goto(
      `/accept-invite?t=${encodeURIComponent(invite.token)}`,
    );
    await expect(
      colleaguePage.getByRole("heading", { name: /accept your invite/i }),
    ).toBeVisible();

    await colleaguePage.getByLabel("Your name").fill(colleague.fullName);
    await colleaguePage
      .getByLabel("Password (min 8 chars)")
      .fill(colleague.password);
    await colleaguePage
      .getByRole("button", { name: /accept invite/i })
      .click();
    await colleaguePage.waitForURL(/\/dashboard/);
    await expect(
      colleaguePage.getByRole("heading", { name: "Patients" }),
    ).toBeVisible();

    // ---- Back in the owner context: both therapists in team list ----
    await ownerPage.goto("/settings/team");
    await expect(
      ownerPage.getByRole("heading", { name: /therapists/i }),
    ).toBeVisible();
    await expect(ownerPage.getByText(owner.email)).toBeVisible();
    await expect(ownerPage.getByText(colleague.email)).toBeVisible();

    await ownerContext.close();
    await colleagueContext.close();
  });
});
