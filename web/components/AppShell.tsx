import Link from "next/link";
import type { ReactNode } from "react";
import type { CurrentUser } from "@/lib/types";

export function AppShell({
  currentUser,
  subscriptionBanner,
  children,
}: {
  currentUser: CurrentUser;
  subscriptionBanner?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4">
          <Link href="/dashboard" className="text-lg font-semibold text-slate-900">
            TherapyRAG
          </Link>
          <nav className="flex gap-4 text-sm text-slate-600">
            <Link href="/dashboard" className="hover:text-slate-900">
              Patients
            </Link>
            <Link href="/settings/team" className="hover:text-slate-900">
              Team
            </Link>
            <Link href="/billing" className="hover:text-slate-900">
              Billing
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm text-slate-500">
            <span>{currentUser.full_name ?? currentUser.email}</span>
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
      {subscriptionBanner}
      <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
    </div>
  );
}
