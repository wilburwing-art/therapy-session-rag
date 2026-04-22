import Link from "next/link";

type Props = {
  status: string;
  trialEndsAt: string | null;
  currentPeriodEnd: string | null;
  isEntitled: boolean;
};

export function SubscriptionBanner({
  status,
  trialEndsAt,
  isEntitled,
}: Props) {
  if (isEntitled && status === "active") return null;

  if (status === "trialing" && trialEndsAt) {
    const daysLeft = Math.max(
      0,
      Math.ceil(
        (new Date(trialEndsAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24),
      ),
    );
    return (
      <div className="border-b border-brand-100 bg-brand-50 px-6 py-3 text-sm text-brand-900">
        You&apos;re on a free trial — {daysLeft} day{daysLeft === 1 ? "" : "s"} left.{" "}
        <Link href="/billing" className="font-medium underline">
          Add a payment method
        </Link>{" "}
        to keep access when it ends.
      </div>
    );
  }

  const copy: Record<string, string> = {
    past_due: "Your last payment failed. Update your card to avoid losing access.",
    unpaid: "Your subscription is unpaid. Update billing to restore access.",
    incomplete: "Your subscription setup is incomplete. Finish checkout to continue.",
    canceled: "Your subscription is canceled. Start a new plan to continue.",
    none: "Start your subscription to activate TherapyRAG.",
  };

  return (
    <div className="border-b border-amber-200 bg-amber-50 px-6 py-3 text-sm text-amber-900">
      {copy[status] ?? "Your subscription needs attention."}{" "}
      <Link href="/billing" className="font-medium underline">
        Open billing
      </Link>
    </div>
  );
}
