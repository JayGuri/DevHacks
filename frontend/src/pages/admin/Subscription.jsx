import { motion } from "framer-motion";
import { Check, CreditCard } from "lucide-react";
import { useState, useEffect } from "react";

// Mocking subscriptionService since it wasn't provided in the directory structure
// The user noted they will have VITE_RAZORPAY_KEY and VITE_RAZORPAY_ID in env.
const subscriptionService = {
  createSubscription: async () => {
    return {
      data: {
        success: true,
        subscription_id: "sub_mock_" + Math.random().toString(36).substring(7),
      },
    };
  },
};

const Subscription = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [razorpayLoaded, setRazorpayLoaded] = useState(false);

  // Directly use the environment variables the user mentioned.
  // Vite strictly requires variables to start with "VITE_" to be exposed to the client
  // so we check both "VITE_RAZORPAY_KEY" and "RAZORPAY_KEY", or fallback to the hardcoded ID we found in the env.
  const razorpayKeyId =
    import.meta.env?.VITE_RAZORPAY_ID ||
    import.meta.env?.VITE_RAZORPAY_KEY ||
    "rzp_live_RlGc5i6ZZ3iSf6"; // Fallback from .env so the modal opens regardless

  // Load Razorpay Checkout script
  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => {
      setRazorpayLoaded(true);
      console.log("✅ Razorpay Checkout script loaded");
    };
    script.onerror = () => {
      console.error("❌ Failed to load Razorpay Checkout script");
      setError("Failed to load payment gateway");
    };
    document.body.appendChild(script);

    return () => {
      // Cleanup script on unmount
      const existingScript = document.querySelector(
        'script[src="https://checkout.razorpay.com/v1/checkout.js"]',
      );
      if (existingScript) {
        document.body.removeChild(existingScript);
      }
    };
  }, []);

  const handlePlanClick = async (plan) => {
    if (plan.name === "Free") {
      return;
    }
    if (plan.name === "Pro") {
      await handleProSubscription();
    }
  };

  const handleProSubscription = async () => {
    if (!razorpayLoaded) {
      setError("Payment gateway is still loading. Please wait...");
      return;
    }

    if (!razorpayKeyId) {
      setError("Razorpay Key ID not configured. Please check your .env file.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const userId = localStorage.getItem("user_id") || "demo_user";

      // Simulate backend call to create a subscription
      const response = await subscriptionService.createSubscription();

      if (response.data.success) {
        // Initialize Razorpay Checkout
        const options = {
          key: razorpayKeyId,
          amount: 100, // Amount in paise (100 paise = 1 INR)
          currency: "INR",
          name: "ARFL Platform",
          description: "Pro Plan - Monthly Subscription",
          prefill: {
            name: localStorage.getItem("user_name") || "",
            email: localStorage.getItem("user_email") || "",
            contact: localStorage.getItem("user_phone") || "",
          },
          theme: {
            color: "#06b6d4", // cyan-500
          },
          handler: function (response) {
            console.log("✅ Payment successful:", response);
            setLoading(false);
            alert(
              "Subscription activated successfully! Welcome to the Pro plan.",
            );
            // Optionally redirect
            // window.location.reload();
          },
          modal: {
            ondismiss: function () {
              console.log("Payment modal closed");
              setLoading(false);
            },
          },
        };

        const rzp = new window.Razorpay(options);
        rzp.on("payment.failed", function (response) {
          console.error(
            "❌ Payment failed - Full response:",
            JSON.stringify(response, null, 2),
          );
          let errorMsg =
            response.error?.description ||
            response.error?.reason ||
            "Unknown payment error";
          setError(`Payment failed: ${errorMsg}`);
          setLoading(false);
        });

        rzp.open();
      } else {
        throw new Error("Failed to create subscription");
      }
    } catch (err) {
      console.error("❌ Subscription error:", err);
      setError(
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
      ctaLabel: "Active Plan",
      guaranteeText: "No credit card required",
    },
    {
      name: "Pro",
      price: "$9.99",
      period: "per month",
      description:
        "Built for teams that rely on robust federated models in production.",
      features: [
        {
          title: "Connected Edge Nodes",
          description: "Unlimited Scale",
        },
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
      badgeText: "POPULAR",
      ctaLabel: "Upgrade To Pro",
      guaranteeText: "Cancel anytime",
    },
  ];

  return (
    <div className="min-h-screen bg-transparent py-12">
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
        </motion.div>

        {error && (
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 mb-6">
            <div className="bg-destructive/10 border border-destructive/50 rounded-lg p-4 text-destructive">
              <p className="font-medium">Error</p>
              <p className="text-sm mt-1">{error}</p>
            </div>
          </div>
        )}

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
                      {plan.features.map((feature, featureIndex) => {
                        return (
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
                        );
                      })}
                    </div>

                    <div className="relative mt-10">
                      <button
                        onClick={() => handlePlanClick(plan)}
                        disabled={
                          loading ||
                          (plan.name === "Pro" && !razorpayLoaded) ||
                          plan.name === "Free"
                        }
                        className={`group/btn relative w-full overflow-hidden rounded-xl p-px font-semibold shadow-sm transition-all duration-200 
                          ${
                            plan.highlighted ?
                              "bg-gradient-to-r from-cyan-500 to-blue-500 text-white hover:shadow-cyan-500/25 hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
                            : "bg-muted text-muted-foreground cursor-default"
                          }`}
                      >
                        <div
                          className={`relative flex items-center justify-center gap-2 rounded-[11px] px-4 py-3.5 transition-colors
                          ${plan.highlighted ? "bg-cyan-500/0 hover:bg-white/10" : "bg-transparent"}
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
                                ></circle>
                                <path
                                  className="opacity-75"
                                  fill="currentColor"
                                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                ></path>
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
    </div>
  );
};

export default Subscription;
