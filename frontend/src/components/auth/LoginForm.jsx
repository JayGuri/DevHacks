import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Mail, Lock, AlertCircle, ArrowRight, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginForm() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm();

  async function onSubmit(data) {
    setError("");
    setSubmitting(true);
    try {
      const user = login(data.email, data.password);
      if (user.role === "TEAM_LEAD") {
        navigate("/admin/overview");
      } else {
        navigate("/dashboard/overview");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full">
      <div className="mb-6">
        <h3 className="text-xl font-display font-bold text-foreground tracking-tight">Sign In</h3>
        <p className="text-muted-foreground text-[12px] mt-1">Access the decentralized control core.</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <AnimatePresence mode="wait">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-2.5 text-[11px] text-destructive font-medium"
            >
              <AlertCircle size={14} />
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="space-y-1.5">
          <Label 
            htmlFor="email" 
            className={`text-[9px] font-mono tracking-widest uppercase transition-colors duration-300 ${focusedField === 'email' ? 'text-primary' : 'text-muted-foreground'}`}
          >
            Email Address
          </Label>
          <div className="relative group">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors duration-300">
              <Mail size={14} />
            </div>
            <Input
              id="email"
              type="email"
              placeholder="lead@arfl.dev"
              onFocus={() => setFocusedField('email')}
              onBlur={() => setFocusedField(null)}
              className="pl-9 bg-background/50 border-white/5 focus:border-primary/50 focus:ring-primary/20 transition-all duration-300 h-10 text-sm"
              {...register("email", {
                required: "Email is required",
                pattern: {
                  value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                  message: "Enter a valid email",
                },
              })}
            />
          </div>
          {errors.email && (
            <motion.p 
              initial={{ opacity: 0, x: -5 }} 
              animate={{ opacity: 1, x: 0 }}
              className="text-[9px] text-destructive font-medium uppercase tracking-wider"
            >
              {errors.email.message}
            </motion.p>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex justify-between items-end">
            <Label 
              htmlFor="password" 
              className={`text-[9px] font-mono tracking-widest uppercase transition-colors duration-300 ${focusedField === 'password' ? 'text-primary' : 'text-muted-foreground'}`}
            >
              Access Secret
            </Label>
            <Link to="#" className="text-[9px] text-primary/60 hover:text-primary transition-colors font-mono tracking-wider">
              RECOVER KEY
            </Link>
          </div>
          <div className="relative group">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors duration-300">
              <Lock size={14} />
            </div>
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="••••••••"
              onFocus={() => setFocusedField('password')}
              onBlur={() => setFocusedField(null)}
              className="pl-9 pr-10 bg-background/50 border-white/5 focus:border-primary/50 focus:ring-primary/20 transition-all duration-300 h-10 text-sm"
              {...register("password", {
                required: "Password is required",
                minLength: {
                  value: 6,
                  message: "Minimum 6 characters",
                },
              })}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary transition-colors"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {errors.password && (
            <motion.p 
              initial={{ opacity: 0, x: -5 }} 
              animate={{ opacity: 1, x: 0 }}
              className="text-[9px] text-destructive font-medium uppercase tracking-wider"
            >
              {errors.password.message}
            </motion.p>
          )}
        </div>

        <div className="pt-2">
          <Button 
            type="submit" 
            className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-display font-bold py-5 group relative overflow-hidden transition-all duration-300 active:scale-[0.98]" 
            disabled={submitting}
          >
            <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
            <span className="relative flex items-center justify-center gap-2 text-sm">
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  AUTHENTICATING...
                </>
              ) : (
                <>
                  INITIALIZE SESSION
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </span>
          </Button>
        </div>

        <div className="text-center pt-1">
          <p className="text-[11px] text-muted-foreground">
            UNAUTHORIZED ACCESS IS PROHIBITED.{" "}
            <Link to="/signup" className="text-primary hover:underline font-bold">
              JOIN NETWORK
            </Link>
          </p>
        </div>
      </form>
    </div>
  );
}
