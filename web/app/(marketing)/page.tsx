import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="bg-slate-50">
      <MarketingNav />
      <Hero />
      <FeatureGrid />
      <PrivacySection />
      <Pricing />
      <FAQ />
      <Footer />
    </div>
  );
}

function MarketingNav() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-4 sm:px-6">
        <Link href="/" className="text-lg font-semibold text-slate-900">
          TherapyRAG
        </Link>
        <nav className="flex items-center gap-2 text-sm sm:gap-4">
          <Link href="/login" className="text-slate-600 hover:text-slate-900">
            Sign in
          </Link>
          <Link
            href="/signup"
            className="rounded-md bg-brand-600 px-3 py-2 text-white hover:bg-brand-700 sm:px-4"
          >
            Start trial
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20 md:py-28">
      <p className="text-sm font-medium uppercase tracking-wider text-brand-700">
        For private-practice therapists
      </p>
      <h1 className="mt-4 max-w-3xl text-3xl font-semibold tracking-tight text-slate-900 sm:text-5xl md:text-6xl">
        Your session notes, homework tracking, and between-session chatbot —
        all from the recording.
      </h1>
      <p className="mt-6 max-w-2xl text-base text-slate-600 sm:text-lg">
        TherapyRAG turns every session recording into a cited summary, a
        running theme map, and a patient-facing chatbot that answers
        questions from your own sessions. No chart-wars, no empty fields.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <Link
          href="/signup"
          className="rounded-lg bg-brand-600 px-6 py-3 text-center text-white hover:bg-brand-700"
        >
          Start 14-day trial
        </Link>
        <a
          href="#features"
          className="rounded-lg border border-slate-300 px-6 py-3 text-center text-slate-700 hover:bg-white"
        >
          See how it works
        </a>
      </div>
      <p className="mt-4 text-sm text-slate-500">
        No credit card needed today. $149/mo after trial.
      </p>
    </section>
  );
}

function FeatureGrid() {
  const features = [
    {
      title: "Session recap in seconds",
      body:
        "Each recording produces a brief, key topics, tone, homework assigned, and flagged risk statements — structured for your notes.",
    },
    {
      title: "Cross-session themes",
      body:
        "Synthesize recurring topics, coping strategies, and ongoing concerns across a patient's history. Auto-refresh as new sessions arrive.",
    },
    {
      title: "Between-session patient chatbot",
      body:
        "Patients get a magic link to ask their own sessions questions. You see what they asked — a live pulse on what's landing.",
    },
  ];
  return (
    <section id="features" className="bg-white py-14 sm:py-20">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          What you get, every session
        </h2>
        <div className="mt-10 grid gap-6 grid-cols-1 sm:grid-cols-2 md:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
            >
              <h3 className="text-lg font-semibold text-slate-900">
                {f.title}
              </h3>
              <p className="mt-2 text-slate-600">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PrivacySection() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
      <div className="grid gap-10 grid-cols-1 md:grid-cols-2">
        <div>
          <p className="text-sm font-medium uppercase tracking-wider text-brand-700">
            HIPAA-aware by default
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            Your patients&apos; data doesn&apos;t leak between practices.
          </h2>
          <p className="mt-4 text-slate-600">
            Every query is scoped to your organization. Consent records are
            append-only with a full audit trail. BAAs are in place with every
            upstream AI and storage vendor.
          </p>
        </div>
        <ul className="space-y-3 text-slate-700">
          <li className="flex gap-2">
            <Check /> Row-level tenant isolation enforced at the DB layer
          </li>
          <li className="flex gap-2">
            <Check /> Append-only consent audit with IP + timestamp
          </li>
          <li className="flex gap-2">
            <Check /> AI safety guardrails: crisis detection, scope limits
          </li>
          <li className="flex gap-2">
            <Check /> SOC 2 Type I in progress; BAAs available on request
          </li>
          <li className="flex gap-2">
            <Check /> Your patient data is never used to train upstream models
          </li>
        </ul>
      </div>
    </section>
  );
}

function Check() {
  return (
    <span
      aria-hidden
      className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white"
    >
      ✓
    </span>
  );
}

function Pricing() {
  return (
    <section className="bg-white py-14 sm:py-20">
      <div className="mx-auto max-w-4xl px-4 sm:px-6">
        <h2 className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">
          One plan, everything included.
        </h2>
        <div className="mt-10 overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
          <div className="grid gap-0 grid-cols-1 md:grid-cols-3">
            <div className="bg-brand-600 p-6 text-white sm:p-8 md:col-span-1">
              <p className="text-sm uppercase tracking-wider opacity-80">
                Practice plan
              </p>
              <p className="mt-2 text-5xl font-semibold">$149</p>
              <p className="mt-1 opacity-80">/ month, per therapist</p>
              <Link
                href="/signup"
                className="mt-6 inline-block rounded-md bg-white px-4 py-3 font-semibold text-brand-700 hover:bg-slate-100"
              >
                Start 14-day trial
              </Link>
            </div>
            <ul className="space-y-3 bg-white p-6 text-slate-700 sm:p-8 md:col-span-2">
              <li className="flex gap-2">
                <Check /> Unlimited session uploads and transcription
              </li>
              <li className="flex gap-2">
                <Check /> Automatic recaps, themes, and chatbot
              </li>
              <li className="flex gap-2">
                <Check /> Patient-facing magic links, no patient account needed
              </li>
              <li className="flex gap-2">
                <Check /> Full consent audit trail
              </li>
              <li className="flex gap-2">
                <Check /> Cancel anytime, self-serve billing portal
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function FAQ() {
  const faqs = [
    {
      q: "Do you replace the therapist?",
      a: "No. TherapyRAG summarizes what was said in the session and answers patient questions from that transcript. It doesn't diagnose, prescribe, or make clinical judgments. You stay in control of the treatment plan.",
    },
    {
      q: "Where is patient data stored?",
      a: "In your dedicated tenant on our HIPAA-aligned infrastructure. Data is encrypted at rest and in transit. BAAs are in place with every upstream AI and storage vendor.",
    },
    {
      q: "How does the chatbot know it's safe?",
      a: "We run a clinical safety guardrail on every input and output. Crisis statements trigger a canned 988 response; the bot won't diagnose, prescribe, or give medical advice.",
    },
    {
      q: "What if I want to leave?",
      a: "Export your session recordings, transcripts, and recaps any time. Cancel from the Stripe customer portal. We delete your data on request.",
    },
  ];
  return (
    <section className="mx-auto max-w-4xl px-4 py-14 sm:px-6 sm:py-20">
      <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
        Common questions
      </h2>
      <dl className="mt-8 space-y-6">
        {faqs.map((item) => (
          <div
            key={item.q}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <dt className="font-semibold text-slate-900">{item.q}</dt>
            <dd className="mt-2 text-slate-600">{item.a}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-10 text-sm text-slate-500">
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 px-4 sm:px-6 md:flex-row md:items-center">
        <p>© {new Date().getFullYear()} TherapyRAG</p>
        <nav className="flex gap-5">
          <Link href="/login">Sign in</Link>
          <a href="mailto:founders@therapyrag.local">Contact</a>
        </nav>
      </div>
    </footer>
  );
}
