import { useRef, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import AnimatedNumber from "@/components/ui/AnimatedNumber";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { fadeInUp, cardHover } from "@/lib/animations";

const BORDER_VARIANTS = {
  default: "border-l-2 border-border",
  success: "border-l-2 border-emerald-500",
  warning: "border-l-2 border-amber-500",
  danger: "border-l-2 border-rose-500",
};

const GRADIENT_VARIANTS = {
  success: "linear-gradient(135deg, hsl(var(--card)) 0%, hsl(142 71% 45% / 0.03) 100%)",
  danger: "linear-gradient(135deg, hsl(var(--card)) 0%, hsl(349 89% 62% / 0.03) 100%)",
  warning: "linear-gradient(135deg, hsl(var(--card)) 0%, hsl(38 92% 50% / 0.03) 100%)",
  default: "none",
};

const StatCard = memo(({
  label,
  value,
  subtext,
  trend,
  icon: Icon,
  color,
  colorVariant = "default",
  loading,
  tooltipText,
  description,
  className,
}) => {
  const borderClass = BORDER_VARIANTS[colorVariant] || BORDER_VARIANTS.default;
  const gradient = GRADIENT_VARIANTS[colorVariant] || GRADIENT_VARIANTS.default;

  const content = (
    <Card 
      className={cn("h-full card-elevated overflow-hidden", borderClass, className)}
      style={{ background: gradient }}
    >
      <CardContent className="p-5 flex flex-col h-full justify-between gap-4">
        {/* Top: Label + Icon */}
        <div className="flex items-center justify-between">
          <p className="metric-label">{label}</p>
          {Icon && (
            <div className="rounded-lg bg-muted/50 p-1.5 border border-border/50">
              <Icon size={14} className="text-muted-foreground" />
            </div>
          )}
        </div>

        {/* Middle: Value */}
        <div className="flex-1">
          {loading ? (
            <Skeleton className="h-10 w-24" />
          ) : (
            <div className={cn("metric-value truncate", color)}>
              {typeof value === "number" ? (
                <AnimatedNumber value={value} decimals={label.includes("Trust") || label.includes("Dist") || (label.includes("Accuracy") && value < 1) ? 3 : 0} />
              ) : value.endsWith("%") && !isNaN(parseFloat(value)) ? (
                <AnimatedNumber value={parseFloat(value)} suffix="%" decimals={label.includes("Accuracy") ? 1 : 0} />
              ) : (
                <span>{value}</span>
              )}
            </div>
          )}
        </div>

        {/* Bottom: Trend + Subtext */}
        <div className="flex flex-col gap-1">
          {trend && !loading && (
            <div
              className={cn(
                "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono leading-none w-fit",
                trend.startsWith("+")
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : trend.startsWith("-")
                    ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                    : "bg-muted text-muted-foreground"
              )}
            >
              {trend.startsWith("+") ? (
                <TrendingUp size={10} />
              ) : trend.startsWith("-") ? (
                <TrendingDown size={10} />
              ) : null}
              {trend}
            </div>
          )}
          {(subtext || description) && !loading && (
            <p className="text-[11px] text-muted-foreground leading-tight">
              {subtext || description}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );

  const wrapper = (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      animate="visible"
      whileHover="hover"
      className="h-full"
    >
      <motion.div variants={cardHover} initial="rest" animate="rest" whileHover="hover" className="h-full">
        {content}
      </motion.div>
    </motion.div>
  );

  if (tooltipText) {
    return (
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>{wrapper}</TooltipTrigger>
          <TooltipContent side="bottom" className="text-xs max-w-[200px]">{tooltipText}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return wrapper;
});

export default StatCard;
