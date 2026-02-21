import LoginForm from "@/components/auth/LoginForm";
import { MOCK_USERS } from "@/lib/mockData";

export default function Login() {
  const lead = MOCK_USERS.find((u) => u.role === "TEAM_LEAD");
  const contributors = MOCK_USERS.filter((u) => u.role === "CONTRIBUTOR");

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-background to-muted px-4">
      <div className="mb-8 text-center">
        <h1 className="text-display text-5xl font-extrabold text-primary">
          ARFL
        </h1>
        <p className="metric-label mt-2 text-muted-foreground">
          Federated Learning Mission Control
        </p>
      </div>

      <div className="mb-6 w-full max-w-md rounded-lg border border-border bg-muted/50 p-4">
        <p className="mb-3 text-sm font-medium text-foreground">
          Demo accounts &middot; password:{" "}
          <code className="mono-data rounded bg-muted px-1.5 py-0.5 text-xs">
            password
          </code>
        </p>
        <div className="space-y-1.5 text-xs text-muted-foreground">
          {lead && (
            <div className="flex items-center justify-between">
              <span className="mono-data">{lead.email}</span>
              <span className="rounded bg-primary/10 px-2 py-0.5 text-primary">
                Team Lead
              </span>
            </div>
          )}
          {contributors.slice(0, 2).map((u) => (
            <div key={u.id} className="flex items-center justify-between">
              <span className="mono-data">{u.email}</span>
              <span className="rounded bg-muted px-2 py-0.5">Contributor</span>
            </div>
          ))}
        </div>
      </div>

      <LoginForm />
    </div>
  );
}
