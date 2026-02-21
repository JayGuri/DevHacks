import SignupForm from "@/components/auth/SignupForm";

export default function Signup() {
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

      <SignupForm />
    </div>
  );
}
