import { expect, test } from "@playwright/test";
import {
  signUpTherapist,
  uniquePatientEmail,
  uniqueTherapist,
} from "./fixtures/accounts";
import { makeSilenceWav } from "./fixtures/audio";

test.describe("consent and session", () => {
  test("therapist adds a patient, grants consent, creates a session, uploads audio", async ({
    page,
  }) => {
    const therapist = uniqueTherapist("session");
    await signUpTherapist(page, therapist);

    // 1. Add a patient.
    await page.goto("/patients/new");
    const patientEmail = uniquePatientEmail();
    await page.getByLabel("Patient's name").fill("Patient Zero");
    await page.getByLabel("Patient's email").fill(patientEmail);
    await page.getByRole("button", { name: /add patient/i }).click();
    await page.waitForURL(/\/patients\/[0-9a-f-]{36}/);

    // 2. Consent panel starts in "needed" state.
    await expect(
      page.getByText(/consent needed before recording sessions/i),
    ).toBeVisible();
    await page.getByRole("button", { name: /record consent/i }).click();

    // Attest and save bulk consent (recording + transcription + ai_analysis).
    await page
      .getByLabel(/i attest that the patient has given informed consent/i)
      .check();
    await page.getByRole("button", { name: /save consent/i }).click();
    await expect(
      page.getByText(
        /consent on file: recording, transcription, ai analysis/i,
      ),
    ).toBeVisible();

    // 3. Start a new session. The button is enabled only once recording
    // consent is active, which is now true.
    await page.getByRole("button", { name: /new session/i }).click();
    await page.waitForURL(/\/sessions\/[0-9a-f-]{36}\/record/);
    await expect(
      page.getByRole("heading", { name: /record or upload session/i }),
    ).toBeVisible();

    // 4. Upload a tiny synthetic WAV. We intercept the upload response
    // so we can assert on it regardless of what the page renders next.
    const wavBuffer = makeSilenceWav(1);
    const uploadResponsePromise = page.waitForResponse(
      (res) =>
        res.url().includes("/api/v1/sessions/") &&
        res.url().endsWith("/recording") &&
        res.request().method() === "POST",
    );

    const fileInput = page.locator('input[type="file"][accept^="audio"]');
    await fileInput.setInputFiles({
      name: "silence.wav",
      mimeType: "audio/wav",
      buffer: wavBuffer,
    });

    const uploadResponse = await uploadResponsePromise;
    expect(uploadResponse.ok()).toBe(true);
    const uploadBody = (await uploadResponse.json()) as {
      recording_path: string;
      status: string;
    };
    expect(uploadBody.recording_path).toBeTruthy();

    // The page posts to /transcribe next and then navigates to the
    // session detail page. We don't care whether transcription
    // actually ran — Deepgram is stubbed out with a placeholder key.
    await page.waitForURL(/\/sessions\/[0-9a-f-]{36}($|\?)/, {
      timeout: 30_000,
    });
  });
});
