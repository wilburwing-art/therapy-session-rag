"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50">
        <main className="mx-auto max-w-xl px-6 py-20 text-center">
          <h1 className="text-2xl font-semibold">Something went wrong.</h1>
          <p className="mt-2 text-slate-600">
            We&apos;ve been notified and are looking into it.
            {error.digest && (
              <span className="block text-xs text-slate-400">
                Ref: {error.digest}
              </span>
            )}
          </p>
          <button
            onClick={reset}
            className="mt-6 rounded-md bg-brand-600 px-4 py-2 text-white hover:bg-brand-700"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
