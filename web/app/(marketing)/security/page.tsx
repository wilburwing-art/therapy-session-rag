import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Security disclosure policy | TherapyRAG",
  description:
    "How to report a vulnerability in TherapyRAG, what is in scope, and our safe-harbor commitment.",
};

const contactEmail =
  process.env.SECURITY_CONTACT_EMAIL ?? "security@therapyrag.local";

export default function SecurityPolicyPage() {
  return (
    <div className="bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <Link href="/" className="text-lg font-semibold text-slate-900">
            TherapyRAG
          </Link>
          <nav className="text-sm">
            <Link href="/" className="text-slate-600 hover:text-slate-900">
              Home
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-4xl font-semibold tracking-tight text-slate-900">
          Security disclosure policy
        </h1>
        <p className="mt-4 text-slate-600">
          TherapyRAG handles protected health information on behalf of
          therapists and their patients. We treat responsible vulnerability
          reports as a collaboration, not a conflict.
        </p>

        <Section title="Reporting a vulnerability">
          <p>
            Email <a className="text-brand-700 underline" href={`mailto:${contactEmail}`}>{contactEmail}</a>
            . Include enough detail that an engineer can reproduce the
            issue from a cold start: endpoint, inputs, observed output,
            expected output. Proof-of-concept code is welcome but not
            required.
          </p>
          <p>
            A matching entry in
            {" "}
            <Link href="/.well-known/security.txt" className="text-brand-700 underline">
              /.well-known/security.txt
            </Link>
            {" "}
            carries the current contact and expiry per RFC 9116.
          </p>
        </Section>

        <Section title="Scope">
          <ul className="list-disc space-y-2 pl-5">
            <li>Production domains ending in <code>therapyrag.com</code>.</li>
            <li>The first-party API at <code>/api/v1/*</code>.</li>
            <li>The patient-facing chatbot and therapist dashboard.</li>
          </ul>
          <p className="mt-3">Out of scope:</p>
          <ul className="mt-2 list-disc space-y-2 pl-5">
            <li>Denial-of-service, rate-limit exhaustion, volumetric abuse.</li>
            <li>Social engineering of TherapyRAG staff or customers.</li>
            <li>Third-party services (Stripe, Resend, Anthropic, OpenAI, Deepgram). Report those directly to the vendor.</li>
            <li>Findings that require prior compromise of a therapist or patient account.</li>
          </ul>
        </Section>

        <Section title="Safe harbor">
          <p>
            If you research in good faith within the scope above, do not
            exfiltrate production data beyond what is needed to demonstrate
            the issue, and give us a reasonable window to remediate before
            public disclosure, TherapyRAG will not pursue legal action or
            ask platforms to remove your research.
          </p>
          <p>
            Report the vulnerability before exploiting it. If you can
            access production PHI during the course of your research, stop
            and tell us.
          </p>
        </Section>

        <Section title="Response times">
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong>Acknowledgment:</strong> within 2 business days of
              your report.
            </li>
            <li>
              <strong>Triage + initial severity:</strong> within 5 business
              days.
            </li>
            <li>
              <strong>Remediation target:</strong> 30 days for high or
              critical findings, 90 days otherwise. We&apos;ll share the
              target with you when we triage.
            </li>
          </ul>
        </Section>

        <Section title="Bug bounty">
          <p>
            TherapyRAG does not operate a paid bug bounty program at this
            time. We do publicly acknowledge researchers who report valid
            findings, with their permission.
          </p>
        </Section>

        <p className="mt-12 text-sm text-slate-500">
          This policy is versioned with the TherapyRAG repository.
        </p>
      </main>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
        {title}
      </h2>
      <div className="mt-3 space-y-3 text-slate-700">{children}</div>
    </section>
  );
}
