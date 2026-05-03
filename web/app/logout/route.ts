import { NextResponse } from "next/server";

const BACKEND_URL = process.env.THERAPYRAG_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const backendRes = await fetch(`${BACKEND_URL}/api/v1/auth/logout`, {
    method: "POST",
    headers: { cookie: cookieHeader },
  });

  const response = NextResponse.redirect(new URL("/login", request.url), 303);
  const setCookie = backendRes.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  else {
    response.cookies.delete("therapyrag_session");
  }
  return response;
}
