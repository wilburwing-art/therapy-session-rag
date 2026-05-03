import { redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { SubscriptionBanner } from "@/components/SubscriptionBanner";
import { serverFetchOrNull } from "@/lib/serverApi";
import type { CurrentUser } from "@/lib/types";

type SubscriptionStatus = {
  subscription_status: string;
  trial_ends_at: string | null;
  current_period_end: string | null;
  has_stripe_customer: boolean;
  is_entitled: boolean;
};

export default async function TherapistLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await serverFetchOrNull<CurrentUser>("/api/v1/auth/me");
  if (!me) redirect("/login");

  const sub = await serverFetchOrNull<SubscriptionStatus>(
    "/api/v1/billing/subscription",
  );

  const banner = sub ? (
    <SubscriptionBanner
      status={sub.subscription_status}
      trialEndsAt={sub.trial_ends_at}
      currentPeriodEnd={sub.current_period_end}
      isEntitled={sub.is_entitled}
    />
  ) : null;

  return (
    <AppShell currentUser={me} subscriptionBanner={banner}>
      {children}
    </AppShell>
  );
}
