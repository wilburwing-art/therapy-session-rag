import { NextResponse } from "next/server";

// Cache-safe rendering: the contents are deterministic, so we let the
// platform cache at the edge. Expiration is recomputed on each build
// because we inline the build-time "now" + 1 year as Expires.
export const dynamic = "force-static";

// Recompute at deploy time. RFC 9116 requires an Expires field; we use
// a 1-year window from the build date, which is the common operator
// default.
const BUILD_EXPIRES = new Date(
  Date.now() + 365 * 24 * 60 * 60 * 1000,
).toISOString();

export function GET(): Response {
  const contact =
    process.env.SECURITY_CONTACT_EMAIL ?? "security@therapyrag.local";
  const origin =
    process.env.NEXT_PUBLIC_WEB_APP_URL ?? "https://therapyrag.com";

  // RFC 9116 fields, one per line, trailing newline.
  const body = [
    `Contact: mailto:${contact}`,
    `Expires: ${BUILD_EXPIRES}`,
    "Preferred-Languages: en",
    `Policy: ${origin}/security`,
    "",
  ].join("\n");

  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
