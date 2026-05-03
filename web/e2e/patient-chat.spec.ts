import { expect, test } from "@playwright/test";
import {
  signUpTherapist,
  uniquePatientEmail,
  uniqueTherapist,
} from "./fixtures/accounts";

test.describe("patient chat", () => {
  test("therapist issues a magic link; patient redeems it and chats", async ({
    browser,
  }) => {
    // ---- Context A: therapist signs up and creates a patient ----
    const therapistContext = await browser.newContext();
    const therapistPage = await therapistContext.newPage();
    const therapist = uniqueTherapist("chat");
    await signUpTherapist(therapistPage, therapist);

    await therapistPage.goto("/patients/new");
    const patientEmail = uniquePatientEmail("chat");
    await therapistPage.getByLabel("Patient's name").fill("Chat Patient");
    await therapistPage.getByLabel("Patient's email").fill(patientEmail);
    await therapistPage
      .getByRole("button", { name: /add patient/i })
      .click();
    await therapistPage.waitForURL(/\/patients\/[0-9a-f-]{36}/);

    // Issue a magic link and capture the raw token from the API response.
    const magicLinkPromise = therapistPage.waitForResponse(
      (res) =>
        res.url().endsWith("/api/v1/auth/patient/magic-link") &&
        res.request().method() === "POST" &&
        res.ok(),
    );
    await therapistPage
      .getByRole("button", { name: /send chatbot link/i })
      .click();
    const magicLinkResponse = await magicLinkPromise;
    const magicLink = (await magicLinkResponse.json()) as {
      token: string;
      expires_at: string;
    };
    expect(magicLink.token).toBeTruthy();

    // ---- Context B: patient opens the magic link and chats ----
    const patientContext = await browser.newContext();
    const patientPage = await patientContext.newPage();

    await patientPage.goto(
      `/chat?t=${encodeURIComponent(magicLink.token)}`,
    );

    // Crisis banner is part of the layout, visible immediately.
    await expect(
      patientPage.getByText(/this chat is not a crisis service/i),
    ).toBeVisible();
    await expect(patientPage.getByText(/988/)).toBeVisible();

    // The chat surface renders after the magic link redeems.
    await expect(
      patientPage.getByRole("heading", { name: /^Hi/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Send a message. With ANTHROPIC_API_KEY=placeholder the backend
    // returns a canned "demo" response instead of calling Claude.
    const chatResponsePromise = patientPage.waitForResponse(
      (res) =>
        res.url().endsWith("/api/v1/chat/patient") &&
        res.request().method() === "POST",
    );
    await patientPage
      .getByPlaceholder(/ask your session history/i)
      .fill("What did we talk about last time?");
    await patientPage.getByRole("button", { name: /^Send$/i }).click();

    const chatResponse = await chatResponsePromise;
    expect(chatResponse.ok()).toBe(true);
    const chatBody = (await chatResponse.json()) as {
      response: string;
      conversation_id: string;
      sources: Array<{ chunk_id: string }>;
    };
    expect(chatBody.response).toBeTruthy();
    expect(chatBody.conversation_id).toBeTruthy();

    // The assistant message renders. We don't assert the exact text
    // because the mock response composes user-supplied content; a
    // non-empty assistant bubble is sufficient.
    const assistantBubble = patientPage.locator(
      "div.bg-white.shadow p.whitespace-pre-wrap",
    );
    await expect(assistantBubble.first()).toBeVisible({ timeout: 15_000 });
    await expect(assistantBubble.first()).not.toHaveText("");

    // If the response includes sources, the citations disclosure renders.
    if (chatBody.sources.length > 0) {
      await expect(
        patientPage.getByText(
          new RegExp(
            `${chatBody.sources.length} source`,
            "i",
          ),
        ),
      ).toBeVisible();
    }

    await therapistContext.close();
    await patientContext.close();
  });
});
