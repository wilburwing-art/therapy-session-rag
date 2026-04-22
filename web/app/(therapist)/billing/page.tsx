import { serverFetch } from "@/lib/serverApi";
import { BillingActions } from "./BillingActions";

type SubscriptionStatus = {
  subscription_status: string;
  trial_ends_at: string | null;
  current_period_end: string | null;
  has_stripe_customer: boolean;
  is_entitled: boolean;
};

const STATUS_LABEL: Record<string, string> = {
  none: "No subscription",
  trialing: "Free trial",
  active: "Active",
  past_due: "Past due",
  incomplete: "Incomplete",
  unpaid: "Unpaid",
  canceled: "Canceled",
};

export default async function BillingPage() {
  const sub = await serverFetch<SubscriptionStatus>(
    "/api/v1/billing/subscription",
  );

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">Billing</h1>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Current plan
        </p>
        <p className="mt-2 text-xl font-medium">TherapyRAG Practice — $149/mo</p>
        <p className="mt-2 text-sm text-slate-600">
          Status:{" "}
          <span className="font-medium text-slate-900">
            {STATUS_LABEL[sub.subscription_status] ?? sub.subscription_status}
          </span>
        </p>
        {sub.trial_ends_at && (
          <p className="mt-1 text-sm text-slate-600">
            Trial ends: {new Date(sub.trial_ends_at).toLocaleDateString()}
          </p>
        )}
        {sub.current_period_end && (
          <p className="mt-1 text-sm text-slate-600">
            Next invoice: {new Date(sub.current_period_end).toLocaleDateString()}
          </p>
        )}

        <BillingActions hasStripeCustomer={sub.has_stripe_customer} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
        <p className="font-semibold text-slate-900">What&apos;s included</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>Unlimited session uploads and transcription</li>
          <li>Automatic session recaps (brief, topics, homework, risk flags)</li>
          <li>Cross-session theme synthesis per patient</li>
          <li>Patient-facing chatbot with between-session review</li>
          <li>Append-only consent audit trail</li>
        </ul>
      </div>
    </div>
  );
}
