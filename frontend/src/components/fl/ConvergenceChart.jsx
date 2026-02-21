import { useMemo } from "react";
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
  fedavg: "#f43f5e",
  trimmed: "#06b6d4",
  median: "#f59e0b",
  grid: "hsl(var(--border))",
  text: "hsl(var(--muted-foreground))",
};

function LegendDot({ color, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="mono-data text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

const CustomDot = (props) => {
  const { cx, cy, index, dataLength } = props;
  if (index === dataLength - 1) {
    return (
      <circle
        cx={cx}
        cy={cy}
        r={4}
        fill={COLORS.trimmed}
        className="animate-pulse-dot"
        style={{ filter: "drop-shadow(0 0 4px #06b6d4)" }}
      />
    );
  }
  return null;
};

export default function ConvergenceChart({ rounds, viewMode }) {
  const data = useMemo(() => rounds || [], [rounds]);

  if (data.length < 2) {
    return <EmptyState icon={Activity} message="Waiting for training data…" />;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="h-full w-full"
    >
      <motion.div
        key={data.length}
        initial={{ clipPath: "inset(0 100% 0 0)" }}
        animate={{ clipPath: "inset(0 0% 0 0)" }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="h-full w-full"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
            <XAxis
              dataKey="round"
              tickFormatter={formatRound}
              tick={{ fontSize: 10, fill: COLORS.text }}
            />
            <YAxis
              tickFormatter={(v) => v + "%"}
              tick={{ fontSize: 10, fill: COLORS.text }}
              domain={[0, 100]}
            />

            {viewMode === "simple" ? (
              <>
                <Tooltip formatter={(v) => formatPercent(v)} />
                <Line
                  dataKey="trimmedAccuracy"
                  stroke={COLORS.trimmed}
                  strokeWidth={2}
                  dot={<CustomDot dataLength={data.length} />}
                  name="Robust Accuracy"
                  isAnimationActive={false}
                />
              </>
            ) : (
              <>
                <Tooltip
                  formatter={(v, name) => [formatPercent(v), name]}
                  labelFormatter={(l) => formatRound(l)}
                />
                <ReferenceLine
                  y={85}
                  stroke={COLORS.grid}
                  strokeDasharray="6 3"
                  label={{
                    value: "Target 85%",
                    fill: COLORS.text,
                    fontSize: 10,
                  }}
                />
                <Line
                  dataKey="fedavgAccuracy"
                  stroke={COLORS.fedavg}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  name="FedAvg"
                  isAnimationActive={false}
                />
                <Line
                  dataKey="trimmedAccuracy"
                  stroke={COLORS.trimmed}
                  strokeWidth={2}
                  dot={<CustomDot dataLength={data.length} />}
                  name="Trimmed Mean"
                  isAnimationActive={false}
                />
                <Line
                  dataKey="medianAccuracy"
                  stroke={COLORS.median}
                  strokeWidth={2}
                  dot={false}
                  name="Coord. Median"
                  isAnimationActive={false}
                />
              </>
            )}
          </LineChart>
        </ResponsiveContainer>
      </motion.div>

      {viewMode === "detailed" && (
        <div className="mt-2 flex flex-wrap gap-4">
          <LegendDot color={COLORS.fedavg} label="FedAvg (no defence)" />
          <LegendDot color={COLORS.trimmed} label="Trimmed Mean" />
          <LegendDot color={COLORS.median} label="Coord. Median" />
        </div>
      )}
    </motion.div>
  );
}
