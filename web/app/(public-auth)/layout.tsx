// Layout for auth pages that must NOT redirect unauthenticated users
// to /login — the pages here are the places they come to get a session.
// Kept intentionally thin so it can co-exist with the root layout.

export default function PublicAuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
