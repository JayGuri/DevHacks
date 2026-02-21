import SignupForm from "@/components/auth/SignupForm";
import { memo } from "react";

const Signup = memo(() => {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background empty-state-bg px-4">
      <div className="mb-12 text-center">
        <h1 className="metric-value text-6xl text-primary tracking-tighter">
          ARFL
        </h1>
        <p className="metric-label mt-3 text-muted-foreground tracking-[0.2em]">
          Mission Orchestrator
        </p>
      </div>

      <div className="w-full max-w-md card-elevated p-8 bg-card/80 backdrop-blur-xl">
        <SignupForm />
      </div>
    </div>
  );
});

export default Signup;
