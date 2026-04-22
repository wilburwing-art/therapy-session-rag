import { defineConfig, devices } from "@playwright/test";

// Base URL for the Next.js web app under test. Override with
// PLAYWRIGHT_BASE_URL when running against a remote environment.
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const IS_CI = !!process.env.CI;

// Limit which browser projects run by default. Full matrix is retained
// for occasional full runs (set PLAYWRIGHT_PROJECTS="chromium,firefox,webkit").
const PROJECT_FILTER = (process.env.PLAYWRIGHT_PROJECTS ?? "chromium")
  .split(",")
  .map((p) => p.trim())
  .filter(Boolean);

const allProjects = [
  { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  { name: "firefox", use: { ...devices["Desktop Firefox"] } },
  { name: "webkit", use: { ...devices["Desktop Safari"] } },
] as const;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e-results",
  fullyParallel: true,
  forbidOnly: IS_CI,
  retries: IS_CI ? 1 : 0,
  workers: IS_CI ? 1 : undefined,
  reporter: IS_CI
    ? [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: allProjects.filter((p) => PROJECT_FILTER.includes(p.name)),
  webServer: {
    // In CI the workflow runs `npm run build` as a separate step, so we
    // just start the prebuilt server here. Locally, `next dev` is fine.
    command: IS_CI ? "npm run start" : "npm run dev",
    url: BASE_URL,
    timeout: 180_000,
    reuseExistingServer: !IS_CI,
    stdout: "pipe",
    stderr: "pipe",
  },
});
