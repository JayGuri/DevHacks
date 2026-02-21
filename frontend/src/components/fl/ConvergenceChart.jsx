import { useMemo, memo } from "react";
import { motion } from "framer-motion";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { formatRound, formatPercent } from "@/lib/utils";
import EmptyState from "@/components/dashboard/EmptyState";
import { Activity } from "lucide-react";

const COLORS = {
  fedavg: "hsl(var(--status-byzantine))",
  trimmed: "hsl(var(--primary))",
  median: "hsl(var(--status-slow))",
  grid: "hsla(var(--border), 0.5)",
  text: "hsl(var(--muted-foreground))",
};

const LegendDot = memo(({ color, label }) => (
  <div className="flex items-center gap-2">
    <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
    <span className="metric-label text-[9px] opacity-70 tracking-widest">{label}</span>
  </div>
));

const CustomDot = (props) => {
  const { cx, cy, index, dataLength } = props;
  if (index === dataLength - 1) {
    return (
      <g>
        <circle cx={cx} cy={cy} r={6} fill={COLORS.trimmed} fillOpacity={0.2} />
        <circle cx={cx} cy={cy} r={3} fill={COLORS.trimmed} className="animate-pulse shadow-lg" />
      </g>
    );
  }
  return null;
};

const ConvergenceChart = memo(({ rounds, viewMode }) => {
  // Performance: Window the data to keep chart snappy
  const data = useMemo(() => {
    if (!rounds) return [];
    return rounds.slice(-40);
  }, [rounds]);

  if (data.length < 2) {
    return <EmptyState icon={Activity} message="Waiting for training data…" />;
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="h-full w-full flex flex-col min-w-0"
    >
      <div className="flex-1 min-h-0 min-w-0 card-base bg-card/10 backdrop-blur-[2px] p-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
            <XAxis
              dataKey="round"
              tickFormatter={formatRound}
              tick={{ fontSize: 9, fill: COLORS.text, fontFamily: "var(--font-mono)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) => v + "%"}
              tick={{ fontSize: 9, fill: COLORS.text, fontFamily: "var(--font-mono)" }}
              domain={[0, 100]}
              axisLine={false}
              tickLine={false}
            />

            <Tooltip 
              contentStyle={{ backgroundColor: "hsl(var(--card))", borderRadius: "12px", border: "1px solid hsl(var(--border))" }}
              itemStyle={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}
              labelStyle={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: "bold" }}
              formatter={(v) => [formatPercent(v), "ACCURACY"]}
              labelFormatter={(l) => `ROUND: ${l}`}
            />

            {viewMode !== "simple" && (
              <ReferenceLine
                y={85}
                stroke={COLORS.grid}
                strokeDasharray="6 3"
                label={{
                  value: "TARGET 85%",
                  fill: COLORS.text,
                  fontSize: 8,
                  fontFamily: "var(--font-mono)",
                  position: "insideBottomRight"
                }}
              />
            )}

            <Line
              dataKey="fedavgAccuracy"
              stroke={COLORS.fedavg}
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              name="FedAvg (Baseline)"
              isAnimationActive={false}
              hide={viewMode === "simple"}
            />
            
            <Line
              dataKey="medianAccuracy"
              stroke={COLORS.median}
              strokeWidth={1.5}
              dot={false}
              name="Median (Robust)"
              isAnimationActive={false}
              hide={viewMode === "simple"}
            />

            <Line
              dataKey="trimmedAccuracy"
              stroke={COLORS.trimmed}
              strokeWidth={2.5}
              dot={<CustomDot dataLength={data.length} />}
              name="Trimmed Mean (Active)"
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {viewMode === "detailed" && (
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 px-1">
          <LegendDot color={COLORS.fedavg} label="FEDAVG BASELINE" />
          <LegendDot color={COLORS.median} label="COORD. MEDIAN" />
          <LegendDot color={COLORS.trimmed} label="ACTIVE AGGREGATOR" />
        </div>
      )}
    </motion.div>
  );
});

export default ConvergenceChart;
