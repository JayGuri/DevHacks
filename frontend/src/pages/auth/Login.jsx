import LoginForm from "@/components/auth/LoginForm";
import { MOCK_USERS } from "@/lib/mockData";
import { memo } from "react";
import { Shield, Zap, Lock } from "lucide-react";

const FeaturePill = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-2">
    <Icon size={14} className="text-cyan-400" />
    <span className="metric-label text-[10px] text-white/80">{label}</span>
  </div>
);

const Login = memo(() => {
  const lead = MOCK_USERS.find((u) => u.role === "TEAM_LEAD");
  const contributors = MOCK_USERS.filter((u) => u.role === "CONTRIBUTOR");

  return (
    <div className="flex min-h-screen">
      {/* Left Panel: Branding (Hidden on mobile) */}
      <div className="hidden lg:flex lg:w-1/2 bg-slate-950 flex-col justify-between p-12 relative overflow-hidden">
        {/* Abstract Background Design */}
        <div className="absolute inset-0 opacity-20 pointer-events-none">
          <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-cyan-500/20 blur-[120px] rounded-full" />
          <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-violet-500/10 blur-[120px] rounded-full" />
          <svg className="absolute inset-0 w-full h-full" width="100%" height="100%">
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" strokeWidth="0.5" strokeOpacity="0.05" />
            </pattern>
            <rect width="100%" height="100%" fill="url(#grid)" />
          </svg>
        </div>

        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 bg-cyan-500 transform rotate-45 rounded-sm shadow-[0_0_20px_rgba(6,182,212,0.5)]" />
            <h1 className="metric-value text-white text-6xl tracking-tighter">ARFL</h1>
          </div>
          <p className="metric-label text-cyan-400 mt-4 tracking-[0.3em]">
            Privacy-Preserving Distributed ML
          </p>
        </div>

        <div className="relative z-10 space-y-8">
          <div className="max-w-md">
            <h2 className="text-white text-3xl font-display font-bold leading-tight">
              Mission control for decentralized intelligence.
            </h2>
            <p className="text-slate-400 mt-4 leading-relaxed">
              Orchestrate robust federated training across untrusted clusters with real-time Byzantine resistance.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <FeaturePill icon={Lock} label="Differential Privacy" />
            <FeaturePill icon={Zap} label="Async Training" />
            <FeaturePill icon={Shield} label="Byzantine Resistance" />
          </div>
        </div>

        <div className="relative z-10 text-slate-500 text-[10px] font-mono tracking-widest uppercase">
          DevHacks // Advanced Agentic Systems // 2026
        </div>
      </div>

      {/* Right Panel: Login Form */}
      <div className="w-full lg:w-1/2 flex flex-col items-center justify-center p-8 bg-background relative overflow-hidden">
        <div className="lg:hidden mb-12 text-center relative z-10">
          <h1 className="metric-value text-primary text-5xl">ARFL</h1>
          <p className="metric-label text-muted-foreground mt-2">Mission Control</p>
        </div>

        <div className="w-full max-w-md relative z-10">
          <LoginForm />

          <div className="mt-8 card-sunken p-6 border-dashed">
            <p className="metric-label mb-4 text-foreground/70">Demo Credentials</p>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-2 rounded-lg bg-background/50 border border-border/50">
                <div>
                  <p className="text-[10px] metric-label opacity-50">Team Lead</p>
                  <p className="mono-data text-xs">{lead?.email}</p>
                </div>
                <code className="text-[10px] font-mono bg-muted px-2 py-1 rounded">password</code>
              </div>
              
              <div className="grid grid-cols-1 gap-2">
                {contributors.slice(0, 2).map((u) => (
                  <div key={u.id} className="flex items-center justify-between p-2 rounded-lg bg-background/50 border border-border/50">
                    <div>
                      <p className="text-[10px] metric-label opacity-50">Contributor</p>
                      <p className="mono-data text-xs">{u.email}</p>
                    </div>
                    <code className="text-[10px] font-mono bg-muted px-2 py-1 rounded">password</code>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Desktop Mobile Pattern */}
        <div className="lg:hidden absolute inset-0 opacity-5 pointer-events-none empty-state-bg" />
      </div>
    </div>
  );
});

export default Login;
