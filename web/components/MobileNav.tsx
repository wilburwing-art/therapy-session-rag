"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type NavLink = { href: string; label: string };

const LINKS: NavLink[] = [
  { href: "/dashboard", label: "Patients" },
  { href: "/search", label: "Search" },
  { href: "/settings/team", label: "Team" },
  { href: "/analytics", label: "Analytics" },
  { href: "/billing", label: "Billing" },
];

export function MobileNav({ userLabel }: { userLabel: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <button
        type="button"
        aria-label="Open navigation menu"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-slate-200 text-slate-700 hover:bg-slate-50 sm:hidden"
      >
        <svg
          aria-hidden="true"
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
        >
          <path
            d="M3 5h14M3 10h14M3 15h14"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
          />
        </svg>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 sm:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
        >
          <div
            className="absolute inset-0 bg-slate-900/50"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute right-0 top-0 flex h-full w-72 max-w-[85vw] flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4">
              <span className="text-base font-semibold text-slate-900">
                Menu
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation menu"
                className="inline-flex h-10 w-10 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100"
              >
                <svg
                  aria-hidden="true"
                  width="18"
                  height="18"
                  viewBox="0 0 18 18"
                  fill="none"
                >
                  <path
                    d="M4 4l10 10M14 4L4 14"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
            <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-3">
              {LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="rounded-md px-3 py-3 text-base text-slate-700 hover:bg-slate-100"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
            <div className="border-t border-slate-200 px-4 py-4 text-sm text-slate-600">
              <p className="truncate">{userLabel}</p>
              <form action="/logout" method="POST" className="mt-3">
                <button
                  type="submit"
                  className="w-full rounded-md border border-slate-200 px-3 py-3 text-slate-700 hover:bg-slate-100"
                >
                  Log out
                </button>
              </form>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
