import { motion } from "framer-motion";
import { formatEpsilon } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

function epsilonColor(eps) {
  if (eps < 3) return "text-emerald-500";
  if (eps < 6) return "text-amber-500";
  return "text-rose-500";
}

function budgetStatus(eps) {
  if (eps < 3) return "Safe";
  if (eps < 6) return "Caution";
  return "Critical";
}

function ArcGauge({ epsilon }) {
  const fraction = Math.min(epsilon / 10, 1);
  const dashTotal = 251;
  const dashOffset = dashTotal * (1 - fraction);

  return (
    <svg viewBox="-10 0 220 130" className="mx-auto w-48">
      <defs>
        <linearGradient id="gauge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#06b6d4" />
          <stop offset="50%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#f43f5e" />
        </linearGradient>
      </defs>
      {/* Track */}
      <path
        d="M 10 100 A 80 80 0 0 1 190 100"
        fill="none"
        className="stroke-border"
        strokeWidth={12}
        strokeLinecap="round"
      />
      {/* Progress */}
      <path
        d="M 10 100 A 80 80 0 0 1 190 100"
        fill="none"
        stroke="url(#gauge-gradient)"
        strokeWidth={12}
        strokeLinecap="round"
        strokeDasharray={dashTotal}
        strokeDashoffset={dashOffset}
      />
      {/* Needle */}
      <line
        x1="100"
        y1="100"
        x2="100"
        y2="30"
        className="stroke-foreground"
        strokeWidth={2}
        strokeLinecap="round"
        transform={`rotate(${-90 + fraction * 180}, 100, 100)`}
      />
      <circle cx="100" cy="100" r="4" className="fill-foreground" />
      {/* Tick labels */}
      <text x="6" y="118" className="fill-muted-foreground" fontSize="10">
        0
      </text>
      <text x="93" y="15" className="fill-muted-foreground" fontSize="10">
        5
      </text>
      <text x="182" y="118" className="fill-muted-foreground" fontSize="10">
        10
      </text>
    </svg>
  );
}

function StatRow({ label, value }) {
  return (
    <div className="flex items-center justify-between">
      <span className="metric-label text-muted-foreground">{label}</span>
      <span className="mono-data text-sm">{value}</span>
    </div>
  );
}

export default function PrivacyGauge({ latestRound, viewMode }) {
  const epsilon = latestRound?.epsilonSpent || 0;
  const color = epsilonColor(epsilon);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {viewMode === "simple" ? (
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex cursor-default flex-col items-center gap-1">
                <span className={`metric-value ${color}`}>
                  {formatEpsilon(epsilon)}
                </span>
                <span className="metric-label text-muted-foreground">
                  Privacy Budget Consumed
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-center">
              <p>
                ε (epsilon) measures privacy cost. Below 3 is safe. Above 6
                means significant risk.
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-col items-center gap-1">
            <span className={`metric-value ${color}`}>
              {formatEpsilon(epsilon)}
            </span>
            <span className="metric-label text-muted-foreground">
              Privacy Budget Consumed
            </span>
          </div>

          <ArcGauge epsilon={epsilon} />

          <div className="space-y-2 rounded-lg border border-border p-3">
            <StatRow label="σ Noise Multiplier" value="0.1" />
            <StatRow label="C Clip Norm" value="1.0" />
            <StatRow
              label="DP Batches"
              value={((latestRound?.round || 0) * 12).toString()}
            />
            <StatRow label="Budget Status" value={budgetStatus(epsilon)} />
          </div>
        </div>
      )}
    </motion.div>
  );
}
