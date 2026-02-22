import LoginForm from "@/components/auth/LoginForm";
import { memo, Suspense } from "react";
import { Shield, Zap, Lock } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import Spline from "@splinetool/react-spline";

const FeaturePill = ({ icon: Icon, label }) => (
  <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-2">
    <Icon size={14} className="text-cyan-400" />
    <span className="metric-label text-[10px] text-white/80 tracking-widest leading-none">
      {label}
    </span>
  </div>
);

const Login = memo(() => {
  const reducedMotion = useReducedMotion();

  return (
    <div className="flex min-h-screen bg-background selection:bg-primary/30 transition-colors duration-500">
      {/* Background Grid Pattern - Fixed to stay behind everything */}
      <div className="fixed inset-0 opacity-[0.03] pointer-events-none z-0">
        <svg className="h-full w-full">
          <pattern
            id="login-grid"
            width="40"
            height="40"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-foreground"
            />
          </pattern>
          <rect width="100%" height="100%" fill="url(#login-grid)" />
        </svg>
      </div>

      {/* Left Panel: 3D Scene - Enhanced with technical decor */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden items-center justify-center transition-colors duration-500">
        {/* Decorative Technical Elements to fill space */}
        <div className="absolute top-12 left-12 space-y-2 z-20 opacity-30">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 bg-cyan-500 rounded-full animate-pulse" />
          </div>
          <div className="font-mono text-[9px] text-slate-500 space-y-1"></div>
        </div>

        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80%] h-[80%] bg-cyan-500/5 blur-[120px] rounded-full pointer-events-none" />

        {!reducedMotion && (
          <motion.div
            className="flex w-full h-screen relative items-center justify-center z-10"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1 }}
          >
            {/* Model "Aura" Glow - Perfectly Centered */}
            <div className="absolute w-[500px] h-[500px] bg-cyan-500/10 blur-[120px] rounded-full animate-pulse pointer-events-none" />

            <div className="w-full h-full relative flex items-center justify-center scale-[1.8] translate-y-[-5%] translate-x-[40%]">
              <Suspense
                fallback={
                  <div className="flex flex-col items-center gap-4">
                    <div className="h-8 w-8 bg-cyan-500 animate-pulse rotate-45 rounded-sm" />
                    <div className="text-cyan-500/50 font-mono text-[10px] tracking-widest animate-pulse">
                      INITIALIZING...
                    </div>
                  </div>
                }
              >
                <Spline
                  className="w-full h-full"
                  scene="https://prod.spline.design/AqJ4j3ogsligEDfj/scene.splinecode"
                  style={{ background: "transparent" }}
                  onLoad={(splineApp) => {
                    if (splineApp.setBackgroundColor) {
                      splineApp.setBackgroundColor("transparent");
                    }
                  }}
                />
              </Suspense>
            </div>
          </motion.div>
        )}

        {/* Subtle Ambient Glows */}
        <div className="absolute inset-0 pointer-events-none opacity-40">
          <div className="absolute top-[-10%] left-[-5%] w-[40%] h-[40%] bg-cyan-500/5 blur-[120px] rounded-full" />
          <div className="absolute bottom-[-10%] right-[-5%] w-[50%] h-[50%] bg-violet-500/5 blur-[120px] rounded-full" />
        </div>
      </div>

      {/* Right Panel: Content & Login Form */}
      <div className="w-full lg:w-1/2 flex flex-col items-center justify-center p-8 lg:p-12 relative z-10 overflow-hidden">
        <div className="w-full max-w-md space-y-8">
          {/* Header Branding Section - Moved from Left to Right per request */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-6"
          >
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 bg-primary transform rotate-45 rounded-sm shadow-[0_0_25px_rgba(var(--primary),0.4)] flex items-center justify-center">
                <div className="h-3 w-3 bg-background rotate-45 rounded-xs" />
              </div>
              <div>
                <h1 className="metric-value text-foreground text-4xl tracking-tighter leading-none">
                  ARFL
                </h1>
                <p className="metric-label text-primary/80 text-[8px] mt-1 tracking-[0.4em]">
                  CONTROL CORE
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <h2 className="text-foreground text-3xl font-display font-bold leading-tight tracking-tight">
                Control{" "}
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-foreground to-foreground/50">
                  Decentralized Intel.
                </span>
              </h2>
              <p className="text-muted-foreground leading-relaxed text-sm max-w-[95%] font-medium">
                Robust federated training with real-time Byzantine resistance.
              </p>
            </div>

            <div className="flex flex-wrap gap-2 pt-1">
              <FeaturePill icon={Lock} label="PRIVACY" />
              <FeaturePill icon={Zap} label="ASYNC" />
              <FeaturePill icon={Shield} label="BYZANTINE" />
            </div>
          </motion.div>

          {/* Login Container - Pushed below the text */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="relative group lg:mt-4"
          >
            {/* Glossy Border Effect */}
            <div className="absolute -inset-[1px] bg-gradient-to-b from-foreground/10 via-foreground/5 to-transparent rounded-2xl -z-10 group-hover:from-primary/20 transition-colors duration-500" />

            <div className="card-base bg-card/30 backdrop-blur-xl border-border/50 p-6 lg:p-8 shadow-2xl rounded-2xl transition-colors duration-500">
              <LoginForm />
            </div>

            {/* Subtle glow behind login box */}
            <div className="absolute -bottom-10 left-1/2 -translate-x-1/2 w-2/3 h-10 bg-primary/5 blur-3xl opacity-30" />
          </motion.div>

          <div className="text-muted-foreground/40 text-[8px] font-mono tracking-[0.3em] uppercase text-center pt-4 opacity-40">
            AUTHENTICATION PROTOCOL v1.0 // 2026
          </div>
        </div>
      </div>
    </div>
  );
});

export default Login;
