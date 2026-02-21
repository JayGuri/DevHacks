import { useMemo, memo } from "react";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  LineChart,
  Line,
  Tooltip as RechartsTooltip,
} from "recharts";
import { formatPercent } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import AnimatedNumber from "@/components/ui/AnimatedNumber";
import { fadeInUp } from "@/lib/animations";

const fprColor = (fpr) => {
  if (fpr > 0.3) return "text-rose-500";
  if (fpr > 0.1) return "text-amber-500";
  return "text-emerald-500";
};

const MetricCard = memo(({ label, value, color, description, isPercent = true }) => {
  return (
    <Card className="flex-1 card-elevated overflow-hidden border-t-2 border-t-primary/20">
      <CardContent className="flex flex-col items-center gap-1 p-5">
        <span className="metric-label opacity-60 text-[9px]">{label}</span>
        <span className={`metric-value text-3xl ${color || ""}`}>
          <AnimatedNumber value={value * (isPercent ? 100 : 1)} suffix={isPercent ? "%" : ""} decimals={isPercent ? 1 : 2} />
        </span>
        {description && (
          <span className="text-center text-[10px] text-muted-foreground font-mono uppercase tracking-tighter opacity-70">
            {description}
          </span>
        )}
      </CardContent>
    </Card>
  );
});

const SABDPanel = memo(({
  latestRound,
  allRounds,
  sabdAlpha,
  viewMode,
  nodes,
}) => {
  const fpr = latestRound?.sabdFPR || 0;
  const recall = latestRound?.sabdRecall || 0;
  const alpha = sabdAlpha ?? 0.5;

  // Divergence histogram: bin cosine distances into 12 buckets 0.0–1.2
  const histogramData = useMemo(() => {
    const bins = Array.from({ length: 12 }, (_, i) => ({
      bin: (i * 0.1).toFixed(1),
      honest: 0,
      byzantine: 0,
    }));
    (nodes || []).forEach((n) => {
      const idx = Math.min(Math.floor(n.cosineDistance / 0.1), 11);
      if (n.isByzantine) bins[idx].byzantine++;
      else bins[idx].honest++;
    });
    return bins;
  }, [nodes]);

  // FPR trend from last 30 rounds
  const fprTrend = useMemo(
    () =>
      (allRounds || []).slice(-30).map((r) => ({
        round: r.round,
        sabdFPR: r.sabdFPR,
      })),
    [allRounds]
  );

  const improvement = (0.72 / Math.max(fpr, 0.01)).toFixed(1);

  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      animate="visible"
      className="space-y-6 min-w-0"
    >
      {/* Metric cards */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <MetricCard
          label="False Positive Rate"
          value={fpr}
          color={fprColor(fpr)}
          description="Detection Error Margin"
        />
        <MetricCard
          label="Recall Efficiency"
          value={recall}
          color="text-emerald-500"
          description="Byzantine Hit Rate"
        />
        <MetricCard
          label="Sensitivity (α)"
          value={alpha}
          isPercent={false}
          color="text-primary"
          description="Activation Threshold"
        />
      </div>

      {viewMode === "detailed" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Divergence histogram */}
          <div className="card-base p-5 bg-card/30 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-6">
              <p className="metric-label opacity-70 text-[10px]">Entropy Distribution</p>
              <span className="badge-public text-[9px]">Cosine Distance</span>
            </div>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogramData}>
                  <XAxis
                    dataKey="bin"
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))", fontFamily: "var(--font-mono)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))", fontFamily: "var(--font-mono)" }}
                    allowDecimals={false}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: "hsl(var(--card))", borderRadius: "12px", border: "1px solid hsl(var(--border))" }}
                    itemStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}
                  />
                  <Bar
                    dataKey="honest"
                    fill="hsl(var(--status-honest))"
                    fillOpacity={0.6}
                    stackId="stack"
                    name="Honest Updates"
                    radius={[2, 2, 0, 0]}
                  />
                  <Bar
                    dataKey="byzantine"
                    fill="hsl(var(--status-byzantine))"
                    fillOpacity={0.6}
                    stackId="stack"
                    name="Byzantine Updates"
                    radius={[2, 2, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* FPR trend */}
          <div className="card-base p-5 bg-card/30 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-6">
              <p className="metric-label opacity-70 text-[10px]">Error Convergence</p>
              <span className="badge-byzantine text-[9px]">FPR Metric</span>
            </div>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={fprTrend}>
                  <XAxis
                    dataKey="round"
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))", fontFamily: "var(--font-mono)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))", fontFamily: "var(--font-mono)" }}
                    domain={[0, 1]}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: "hsl(var(--card))", borderRadius: "12px", border: "1px solid hsl(var(--border))" }}
                    itemStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}
                  />
                  <Line
                    dataKey="sabdFPR"
                    stroke="hsl(var(--status-byzantine))"
                    strokeWidth={2}
                    dot={false}
                    name="FPR"
                    animationDuration={1500}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Callout */}
          <div className="md:col-span-2 card-sunken p-4 flex items-center justify-between border-dashed">
            <div className="flex items-center gap-3">
              <div className="h-2 w-2 rounded-full bg-primary pulse-dot" />
              <p className="text-xs text-muted-foreground font-mono">
                SABD EFFICIENCY REDUCTION: <span className="text-foreground font-bold">{improvement}×</span> RELATIVE TO BASELINE (α={alpha})
              </p>
            </div>
            <div className="metric-label text-[9px] opacity-40">Privacy Protected</div>
          </div>
        </div>
      )}
    </motion.div>
  );
});

export default SABDPanel;
