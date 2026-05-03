import Link from "next/link";

// Shared layout for every /patient route (chat, homework, sessions,
// recap detail, ...). Intentionally client-agnostic: each page owns its
// own auth/magic-link redemption flow because /chat needs to read the
// `?t=...` token from the URL. The layout only provides the chrome:
// crisis banner, a simple nav strip, and the page container.

export default function PatientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-slate-50">
      <CrisisBanner />
      <PatientNav />
      {children}
    </div>
  );
}

function CrisisBanner() {
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900">
      This chat is not a crisis service. If you&apos;re in danger, call or text{" "}
      <strong>988</strong> (US) or your local emergency number.
    </div>
  );
}

function PatientNav() {
  return (
    <nav
      aria-label="Patient navigation"
      className="border-b border-slate-200 bg-white"
    >
      <div className="mx-auto flex max-w-3xl items-center gap-4 px-4 py-3 text-sm">
        <Link
          href="/chat"
          className="font-semibold text-slate-900 hover:text-brand-700"
        >
          TherapyRAG
        </Link>
        <div className="ml-auto flex items-center gap-4 text-slate-600">
          <Link href="/chat" className="hover:text-slate-900">
            Chat
          </Link>
          <Link href="/sessions" className="hover:text-slate-900">
            Sessions
          </Link>
          <Link href="/homework" className="hover:text-slate-900">
            Homework
          </Link>
        </div>
      </div>
    </nav>
  );
}
