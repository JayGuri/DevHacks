import LoginForm from "@/components/auth/LoginForm";
import { memo, Suspense, useState, useEffect } from "react";
import { Shield, Zap, Lock, Activity, Globe, Cpu } from "lucide-react";
import { motion, useReducedMotion, AnimatePresence } from "framer-motion";
import Spline from '@splinetool/react-spline';

const FeaturePill = ({ icon: Icon, label, color = "text-cyan-400" }) => (
  <motion.div 
    whileHover={{ y: -2, scale: 1.02 }}
    className="flex items-center gap-2 bg-white/5 backdrop-blur-md border border-white/10 rounded-full px-4 py-2 shadow-[0_0_15px_rgba(0,0,0,0.2)]"
  >
    <Icon size={14} className={color} />
    <span className="metric-label text-[10px] text-white/80 tracking-[0.2em] leading-none font-bold">{label}</span>
  </motion.div>
);

const TechOverlay = () => (
  <div className="absolute inset-0 pointer-events-none overflow-hidden z-20">
    <div className="absolute top-12 left-12 space-y-4 opacity-40">
      <div className="flex items-center gap-3">
        <div className="h-2 w-2 bg-primary rounded-full animate-pulse" />
        <div className="h-[1px] w-24 bg-gradient-to-r from-primary to-transparent" />
        <span className="font-mono text-[10px] text-primary tracking-widest uppercase">System Online</span>
      </div>
      <div className="space-y-1 font-mono text-[9px] text-slate-500">
        <p className="flex justify-between gap-4"><span>COORDS:</span> <span className="text-slate-400">40.7128° N, 74.0060° W</span></p>
        <p className="flex justify-between gap-4"><span>UPTIME:</span> <span className="text-slate-400">99.9982%</span></p>
        <p className="flex justify-between gap-4"><span>NODES:</span> <span className="text-slate-400">14,282 ACTIVE</span></p>
      </div>
    </div>

    <div className="absolute bottom-12 right-12 text-right space-y-4 opacity-40">
      <div className="space-y-1 font-mono text-[9px] text-slate-500">
        <p>ENCRYPTION: AES-256-GCM</p>
        <p>PROTOCOL: ARFL-v1.0.4</p>
      </div>
      <div className="flex items-center justify-end gap-3">
        <span className="font-mono text-[10px] text-primary tracking-widest uppercase">Satellite Uplink</span>
        <div className="h-[1px] w-24 bg-gradient-to-l from-primary to-transparent" />
        <div className="h-2 w-2 bg-primary rounded-full animate-pulse shadow-[0_0_8px_hsl(var(--primary)/0.8)]" />
      </div>
    </div>

    <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.1)_50%),linear-gradient(90deg,rgba(255,0,0,0.03),rgba(0,255,0,0.01),rgba(0,0,255,0.03))] z-30 pointer-events-none opacity-20 bg-[length:100%_2px,3px_100%]" />
  </div>
);

const Login = memo(() => {
  const reducedMotion = useReducedMotion();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="h-screen bg-[#000000] selection:bg-primary/30 overflow-hidden font-sans relative">
      {/* GLOBAL BACKGROUND ELEMENTS (Consistent for both sides) */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        {/* Core background color - Pure Black to match Spline Scene */}
        <div className="absolute inset-0 bg-[#000000]" />
        
        {/* Unified Grid Pattern - Now covers full screen */}
        <div 
          className="absolute inset-0 opacity-[0.05]" 
          style={{ 
            backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
            backgroundSize: '40px 40px' 
          }} 
        />
      </div>

      <div className="flex h-full relative z-10 overflow-hidden">
        {/* Left Panel: 3D Scene */}
        <div className="hidden lg:flex lg:w-[55%] relative overflow-hidden items-center justify-center border-r border-white/5 bg-transparent">
          <TechOverlay />
          
          {/* Glow Effects (Scoped to left side) */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] bg-primary/10 blur-[180px] rounded-full pointer-events-none animate-pulse" />
          
          <AnimatePresence>
            {mounted && !reducedMotion && (
              <motion.div
                className="flex w-full h-full relative items-center justify-center z-10"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 1.5, ease: "easeOut" }}
              >
                {/* 
                   ADJUSTMENT MARKER: 
                   To change model size: edit 'scale-[1.2]'
                   To change model position: add 'translate-x-[X%]' or 'translate-y-[Y%]'
                */}
                <div className="w-full h-full relative flex items-center translate-x-[22.5%] justify-center scale-[1.2] transition-transform duration-500">
                  <Suspense
                    fallback={
                      <div className="flex flex-col items-center gap-6">
                        <div className="h-12 w-12 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                        <div className="text-primary/50 font-mono text-xs tracking-[0.5em] animate-pulse">
                          SYNCING CORE...
                        </div>
                      </div>
                    }
                  >
                    <Spline
                      className="w-full h-full"
                      scene="https://prod.spline.design/AqJ4j3ogsligEDfj/scene.splinecode"
                      style={{ background: "transparent" }}
                    />
                  </Suspense>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right Panel: Content & Login Form */}
        <div className="w-full lg:w-[45%] flex flex-col items-center justify-between p-6 lg:p-8 relative bg-transparent">
          {/* Main Content Area */}
          <div className="w-full flex flex-col items-center flex-1 justify-center space-y-6 lg:space-y-8 min-h-0">
            {/* Header Branding Section */}
            <motion.div 
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, ease: "easeOut" }}
              className="space-y-5 lg:space-y-6 w-full max-w-[420px]"
            >
              <div className="flex items-center gap-3 group">
                <div className="h-10 w-10 bg-gradient-to-br from-primary via-primary to-cyan-300 transform rotate-45 rounded-lg shadow-[0_0_25px_hsl(var(--primary)/0.4)] flex items-center justify-center transition-transform duration-500 group-hover:rotate-[135deg]">
                  <div className="h-3 w-3 bg-[#020408] rotate-45 rounded-sm" />
                </div>
                <div>
                  <h1 className="text-display text-2xl lg:text-3xl font-black text-white tracking-tighter leading-none">ARFL<span className="text-primary">.</span></h1>
                  <p className="metric-label text-primary/60 text-[8px] mt-1 tracking-[0.5em] font-bold">DECENTRALIZED INTELLIGENCE</p>
                </div>
              </div>
              
              <div className="space-y-2 lg:space-y-3">
                <h2 className="text-white text-2xl lg:text-3xl font-display font-bold leading-tight tracking-tight">
                  Secure your <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-cyan-300">Federated Edge.</span>
                </h2>
                <p className="text-slate-400 leading-relaxed text-[11px] lg:text-xs max-w-[90%] font-medium">
                  The most robust federated training framework for sensitive data environments, featuring real-time Byzantine resistance.
                </p>
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                <FeaturePill icon={Lock} label="PRIVACY" color="text-cyan-400" />
                <FeaturePill icon={Activity} label="REALTIME" color="text-emerald-400" />
                <FeaturePill icon={Cpu} label="NEURAL" color="text-violet-400" />
              </div>
            </motion.div>

            {/* Login Container */}
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
              className="relative w-full max-w-[420px]"
            >
              {/* External Glow Border */}
              <div className="absolute -inset-[1px] bg-gradient-to-b from-white/20 via-white/5 to-transparent rounded-3xl -z-10" />
              
              {/* Glass Container */}
              <div className="bg-[#0a0c10]/40 backdrop-blur-3xl border border-white/5 p-6 lg:p-7 rounded-[20px] relative overflow-hidden group shadow-[0_20px_50px_rgba(0,0,0,0.5)]">
                <motion.div 
                  className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-primary/50 to-transparent"
                  animate={{ x: ['-100%', '100%'] }}
                  transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                />
                
                <LoginForm />
              </div>
            </motion.div>
          </div>

          {/* Explicitly Fixed Footer Wrapper */}
          <motion.div 
            className="w-full max-w-[420px] pt-4 mt-auto"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8 }}
          >
            <div className="flex items-center justify-between border-t border-white/5 pt-4">
              <div className="text-slate-600 text-[8px] font-mono tracking-widest uppercase">
                Auth System v1.0.4 r72
              </div>
              <div className="flex gap-3">
                <span className="h-1 w-1 bg-emerald-500 rounded-full animate-pulse" />
                <span className="h-1 w-1 bg-slate-800 rounded-full" />
                <span className="h-1 w-1 bg-slate-800 rounded-full" />
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
});

export default Login;
