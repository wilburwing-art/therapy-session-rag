import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TherapyRAG — AI co-pilot for therapists",
  description:
    "Automatic session summaries, cross-session themes, and a patient-facing AI chatbot — for licensed therapists in private practice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
