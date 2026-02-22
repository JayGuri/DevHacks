import { motion } from "framer-motion";
import { Check, CreditCard } from "lucide-react";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { USE_MOCK } from "@/lib/config";
import { apiFetch, setToken } from "@/lib/api";
import AppLayout from "@/components/layout/AppLayout";

const Subscription = () => {
  const { currentUser, updateUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [razorpayLoaded, setRazorpayLoaded] = useState(false);

  const razorpayKeyId =
    import.meta.env?.VITE_RAZORPAY_ID ||
    import.meta.env?.VITE_RAZORPAY_KEY ||
    "rzp_test_mock";

  const isPro = currentUser?.subscriptionTier === "PRO";

  // Load Razorpay Checkout script
  useEffect(() => {
    const existing = document.querySelector(
      'script[src="https://checkout.razorpay.com/v1/checkout.js"]',
    );
    if (existing) {
      setRazorpayLoaded(true);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => setRazorpayLoaded(true);
    script.onerror = () => toast.error("Failed to load payment gateway");
    document.body.appendChild(script);
    return () => {
      const s = document.querySelector(
        'script[src="https://checkout.razorpay.com/v1/checkout.js"]',
      );
      if (s) document.body.removeChild(s);
    };
  }, []);

  /** Called after Razorpay confirms payment — upgrades tier in backend and updates local state. */
  async function activateProTier() {
    if (USE_MOCK) {
      // In mock mode: simulate upgrade locally so the UI responds immediately
      const upgraded = { ...currentUser, subscriptionTier: "PRO" };
      updateUser(upgraded);
      toast.success("Pro plan activated! (mock mode)");
      return;
    }

    try {
      const data = await apiFetch("/auth/subscription", {
        method: "PATCH",
        body: JSON.stringify({ tier: "PRO" }),
      });
      // Update token so new JWT (with tier=PRO) is used for subsequent requests
      setToken(data.token);
      // Update in-memory + localStorage user object — Pro features unlock immediately
      updateUser(data.user);
      toast.success("Pro plan activated! All Pro features are now unlocked.");
    } catch (err) {
      console.error("Subscription upgrade failed:", err);
      toast.error(
        "Upgrade recorded in payment but failed to activate. Please contact support.",
      );
    }
  }

  const handlePlanClick = async (plan) => {
    if (plan.name === "Free" || isPro) return;
    if (plan.name === "Pro") await handleProSubscription();
  };

  const handleProSubscription = async () => {
    if (!razorpayLoaded) {
      toast.error("Payment gateway is still loading. Please wait...");
      return;
    }
    if (!razorpayKeyId) {
      toast.error(
        "Razorpay Key ID not configured. Please check your .env file.",
      );
      return;
    }

    setLoading(true);

    try {
      const options = {
        key: razorpayKeyId,
        amount: 99900, // 999 INR in paise
        currency: "INR",
        name: "ARFL Platform",
        description: "Pro Plan — Monthly Subscription",
        prefill: {
          name: currentUser?.name || "",
          email: currentUser?.email || "",
          contact: "",
        },
        theme: { color: "#06b6d4" },
        handler: async function (response) {
          console.log("✅ Payment successful:", response.razorpay_payment_id);
          await activateProTier();
          setLoading(false);
        },
        modal: {
          ondismiss: function () {
            setLoading(false);
          },
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.on("payment.failed", function (response) {
        const errorMsg =
          response.error?.description ||
          response.error?.reason ||
          "Unknown error";
        toast.error(`Payment failed: ${errorMsg}`);
        setLoading(false);
      });
      rzp.open();
    } catch (err) {
      console.error("❌ Subscription error:", err);
      toast.error(
        err.message || "Failed to initiate subscription. Please try again.",
      );
      setLoading(false);
    }
  };

  const plans = [
    {
      name: "Free",
      price: "$0",
      period: "forever",
      description: "Great for academic testing and local environments.",
      features: [
        { title: "Connected Edge Nodes", description: "Up to 5 nodes" },
        { title: "Aggregation Rules", description: "Standard FedAvg only" },
        {
          title: "Dashboard Analytics",
          description: "Basic 2D Telemetry & Logs",
        },
      ],
      ctaLabel: isPro ? "Downgrade to Free" : "Active Plan",
      guaranteeText: "No credit card required",
    },
    {
      name: "Pro",
      price: "$9.99",
      period: "per month",
      description:
        "Built for teams that rely on robust federated models in production.",
      features: [
        { title: "Connected Edge Nodes", description: "Unlimited Scale" },
        {
          title: "Aggregation Rules",
          description: "Multi-Krum, Trimmed Mean, Median",
        },
        {
          title: "Dashboard Analytics",
          description: "Real-time 3D Topology & Node Reports",
        },
      ],
      highlighted: true,
      badgeText: isPro ? "ACTIVE" : "POPULAR",
      ctaLabel: isPro ? "Current Plan" : "Upgrade To Pro",
      guaranteeText: "Cancel anytime",
    },
  ];

  return (
    <AppLayout title="Billing">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center justify-center p-2 rounded-full bg-cyan-500/10 mb-4">
            <CreditCard className="w-6 h-6 text-cyan-500" />
          </div>
          <h1 className="text-4xl font-bold text-foreground mb-4">
            Choose Your Plan
          </h1>
          <p className="text-muted-foreground text-lg">
            Scale your asynchronous federated learning securely.
          </p>
          {isPro && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-4 py-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400">
              <Check className="h-4 w-4" /> You are on the Pro plan
            </div>
          )}
        </motion.div>

        <div className="flex flex-col md:flex-row gap-8 justify-center items-stretch max-w-4xl mx-auto">
          {plans.map((plan, index) => (
            <motion.div
              key={plan.name}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className="flex h-full w-full justify-center max-w-md"
            >
              <div className="group relative w-full h-full">
                <div className="relative h-full overflow-hidden rounded-2xl bg-card border border-border/50 shadow-2xl transition-all duration-300 hover:-translate-y-2 hover:shadow-cyan-500/10 hover:border-cyan-500/30">
                  <div
                    className={`absolute inset-0 bg-gradient-to-b ${
                      plan.highlighted ?
                        "from-cyan-500/5 to-blue-500/5 opacity-100"
                      : "from-accent/5 to-transparent opacity-100"
                    }`}
                  />
                  <div className="relative flex h-full flex-col rounded-2xl p-8 z-10">
                    {plan.highlighted && (
                      <>
                        <div className="absolute -left-16 -top-16 h-32 w-32 rounded-full bg-gradient-to-br from-cyan-500/10 to-transparent blur-2xl transition-all duration-500 group-hover:scale-150" />
                        <div className="absolute -bottom-16 -right-16 h-32 w-32 rounded-full bg-gradient-to-br from-blue-500/10 to-transparent blur-2xl transition-all duration-500 group-hover:scale-150" />
                      </>
                    )}

                    {plan.badgeText && (
                      <div className="absolute -right-[1px] -top-[1px] overflow-hidden rounded-tr-2xl">
                        <div className="absolute h-20 w-20 bg-gradient-to-r from-cyan-500 to-blue-500" />
                        <div className="absolute h-20 w-20 bg-background/90" />
                        <div className="absolute right-0 top-[22px] h-[2px] w-[56px] rotate-45 bg-gradient-to-r from-cyan-500 to-blue-500" />
                        <span className="absolute right-1 top-1 text-[10px] font-semibold text-foreground">
                          {plan.badgeText}
                        </span>
                      </div>
                    )}

                    <div className="relative">
                      <h3 className="text-sm font-semibold uppercase tracking-wider text-cyan-500">
                        {plan.name}
                      </h3>
                      <div className="mt-4 flex items-baseline gap-2">
                        <span className="text-4xl font-bold tracking-tight text-foreground">
                          {plan.price}
                        </span>
                        {plan.period && (
                          <span className="text-sm font-medium text-muted-foreground">
                            /{plan.period}
                          </span>
                        )}
                      </div>
                      {plan.description && (
                        <p className="mt-4 min-h-[48px] text-sm text-muted-foreground leading-relaxed">
                          {plan.description}
                        </p>
                      )}
                    </div>

                    <div className="relative mt-8 flex-1 space-y-5 border-t border-border/50 pt-8">
                      {plan.features.map((feature, featureIndex) => (
                        <div
                          key={`${plan.name}-feature-${featureIndex}`}
                          className="flex items-start gap-4"
                        >
                          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-500/10 mt-0.5">
                            <Check className="h-4 w-4 text-cyan-500" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-foreground">
                              {feature.title}
                            </p>
                            {feature.description && (
                              <p className="text-xs text-muted-foreground mt-1">
                                {feature.description}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="relative mt-10">
                      <button
                        onClick={() => handlePlanClick(plan)}
                        disabled={
                          loading ||
                          (plan.name === "Pro" && !razorpayLoaded) ||
                          plan.name === "Free" ||
                          (plan.name === "Pro" && isPro)
                        }
                        className={`group/btn relative w-full overflow-hidden rounded-xl p-px font-semibold shadow-sm transition-all duration-200
                          ${
                            plan.highlighted && !isPro ?
                              "bg-gradient-to-r from-cyan-500 to-blue-500 text-white hover:shadow-cyan-500/25 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                            : "bg-muted text-muted-foreground cursor-default"
                          }`}
                      >
                        <div
                          className={`relative flex items-center justify-center gap-2 rounded-[11px] px-4 py-3.5 transition-colors
                            ${plan.highlighted && !isPro ? "bg-cyan-500/0 hover:bg-white/10" : "bg-transparent"}
                          `}
                        >
                          {loading && plan.name === "Pro" ?
                            <>
                              <svg
                                className="animate-spin h-4 w-4"
                                xmlns="http://www.w3.org/2000/svg"
                                fill="none"
                                viewBox="0 0 24 24"
                              >
                                <circle
                                  className="opacity-25"
                                  cx="12"
                                  cy="12"
                                  r="10"
                                  stroke="currentColor"
                                  strokeWidth="4"
                                />
                                <path
                                  className="opacity-75"
                                  fill="currentColor"
                                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                />
                              </svg>
                              Processing...
                            </>
                          : <>{plan.ctaLabel}</>}
                        </div>
                      </button>
                    </div>

                    {plan.guaranteeText && (
                      <div className="mt-6 flex items-center justify-center gap-2 text-muted-foreground">
                        <span className="text-xs font-medium">
                          {plan.guaranteeText}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </AppLayout>
  );
};

export default Subscription;
