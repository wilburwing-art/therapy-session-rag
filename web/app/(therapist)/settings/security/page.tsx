import { serverFetch } from "@/lib/serverApi";
import { SecurityForm } from "./SecurityForm";

type CurrentUser = {
  id: string;
  organization_id: string;
  email: string;
  role: string;
  full_name: string | null;
  email_verified_at: string | null;
};

export default async function SecurityPage() {
  const me = await serverFetch<CurrentUser>("/api/v1/auth/me");

  // The /auth/me endpoint intentionally doesn't leak 2FA state — we
  // infer it on the client by attempting enrollment and handling the
  // 409 ("already enabled") response there. Passing the email here
  // so the client can display context.
  return (
    <div className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Security</h1>
        <p className="mt-1 text-sm text-slate-600">
          Add a second factor to your account. Signed in as {me.email}.
        </p>
      </header>
      <SecurityForm />
    </div>
  );
}
