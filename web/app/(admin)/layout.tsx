import Link from "next/link";
import { redirect } from "next/navigation";
import { serverFetchOrNull } from "@/lib/serverApi";
import type { CurrentUser } from "@/lib/types";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await serverFetchOrNull<CurrentUser>("/api/v1/auth/me");
  if (!me) redirect("/login");
  if (me.role !== "admin") redirect("/dashboard");

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4">
          <Link
            href="/admin/orgs"
            className="text-lg font-semibold text-slate-900"
          >
            TherapyRAG Admin
          </Link>
          <nav className="flex gap-4 text-sm text-slate-600">
            <Link href="/admin/orgs" className="hover:text-slate-900">
              Orgs
            </Link>
            <Link href="/admin/events" className="hover:text-slate-900">
              Events
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm text-slate-500">
            <Link href="/dashboard" className="hover:text-slate-900">
              Back to dashboard
            </Link>
            <span className="text-slate-300">|</span>
            <span>{me.full_name ?? me.email}</span>
            <form action="/logout" method="POST">
              <button
                type="submit"
                className="rounded-md border border-slate-200 px-3 py-1 text-slate-600 hover:bg-slate-100"
              >
                Log out
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
    </div>
  );
}
