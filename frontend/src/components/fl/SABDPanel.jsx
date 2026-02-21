import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  LineChart,
  Line,
  Tooltip,
} from "recharts";
import { formatPercent } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import AnimatedNumber from "@/components/ui/AnimatedNumber";
import { fadeInUp } from "@/lib/animations";

function fprColor(fpr) {
  if (fpr > 0.3) return "text-rose-500";
  if (fpr > 0.1) return "text-amber-500";
  return "text-emerald-500";
}

function MetricCard({ label, value, color, description, isPercent = true }) {
  return (
    <Card className="flex-1">
      <CardContent className="flex flex-col items-center gap-1 p-4">
        <span className="metric-label text-muted-foreground">{label}</span>
        <span className={`metric-value ${color || ""}`}>
          <AnimatedNumber value={value * (isPercent ? 100 : 1)} suffix={isPercent ? "%" : ""} decimals={isPercent ? 1 : 2} />
        </span>
        {description && (
          <span className="text-center text-xs text-muted-foreground">
            {description}
          </span>
        )}
      </CardContent>
    </Card>
  );
}

export default function SABDPanel({
  latestRound,
  allRounds,
  sabdAlpha,
  viewMode,
  nodes,
}) {
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
      className="space-y-4"
    >
      {/* Metric cards */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <MetricCard
          label="False Positive Rate"
          value={fpr}
          color={fprColor(fpr)}
          description="Lower is better"
        />
        <MetricCard
          label="Recall"
          value={recall}
          color="text-emerald-500"
          description="Byzantine detection rate"
        />
        <MetricCard
          label="Alpha (α)"
          value={alpha}
          isPercent={false}
          color="text-primary"
          description="Sensitivity threshold"
        />
      </div>

      {viewMode === "detailed" && (
        <>
          {/* Divergence histogram */}
          <div className="rounded-lg border border-border p-3">
            <p className="metric-label mb-2 text-muted-foreground">
              Cosine Distance Distribution
            </p>
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogramData}>
                  <XAxis
                    dataKey="bin"
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                  />
                  <YAxis
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                    allowDecimals={false}
                  />
                  <Tooltip />
                  <Bar
                    dataKey="honest"
                    fill="#f59e0b80"
                    stackId="stack"
                    name="Honest / Slow"
                  />
                  <Bar
                    dataKey="byzantine"
                    fill="#f43f5e80"
                    stackId="stack"
                    name="Byzantine"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* FPR trend */}
          <div className="rounded-lg border border-border p-3">
            <p className="metric-label mb-2 text-muted-foreground">
              FPR Trend (last 30 rounds)
            </p>
            <div className="h-24">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={fprTrend}>
                  <XAxis
                    dataKey="round"
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                  />
                  <YAxis
                    tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                    domain={[0, 1]}
                  />
                  <Line
                    dataKey="sabdFPR"
                    stroke="#f43f5e"
                    strokeWidth={1.5}
                    dot={false}
                    name="FPR"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Callout */}
          <div className="rounded-lg bg-muted p-3">
            <p className="text-sm text-muted-foreground">
              SABD reduced false positives{" "}
              <span className="font-medium text-foreground">
                {improvement}×
              </span>{" "}
              vs baseline (α = {alpha})
            </p>
          </div>
        </>
      )}
    </motion.div>
  );
}
