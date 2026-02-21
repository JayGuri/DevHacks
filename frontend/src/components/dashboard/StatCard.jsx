import { useRef } from "react";
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

export default function StatCard({
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
}) {
  const borderClass = BORDER_VARIANTS[colorVariant] || BORDER_VARIANTS.default;

  const content = (
    <Card className={cn("h-full", borderClass, className)}>
      <CardContent className="relative flex items-start gap-3 p-5">
        {Icon && (
          <div className="rounded-md bg-primary/10 p-2">
            <Icon size={18} className="text-primary" />
          </div>
        )}
        <div className="flex-1">
          {loading ? (
            <>
              <Skeleton className="mb-2 h-3 w-20" />
              <Skeleton className="h-8 w-24" />
            </>
          ) : (
            <>
              <p className="metric-label text-muted-foreground">{label}</p>
              <div className={cn("metric-value mt-0.5", color)}>
                {typeof value === "number" ? (
                  <AnimatedNumber value={value} decimals={label.includes("Trust") || label.includes("Dist") ? 3 : 0} />
                ) : value.endsWith("%") && !isNaN(parseFloat(value)) ? (
                  <AnimatedNumber value={parseFloat(value)} suffix="%" decimals={label.includes("Accuracy") ? 1 : 0} />
                ) : (
                  <span>{value}</span>
                )}
              </div>
              {(subtext || description) && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {subtext || description}
                </p>
              )}
              {trend && (
                <div
                  className={cn(
                    "mt-1 flex items-center gap-1 text-xs",
                    trend.startsWith("+")
                      ? "text-emerald-500"
                      : trend.startsWith("-")
                        ? "text-rose-500"
                        : "text-muted-foreground"
                  )}
                >
                  {trend.startsWith("+") ? (
                    <TrendingUp size={12} />
                  ) : trend.startsWith("-") ? (
                    <TrendingDown size={12} />
                  ) : null}
                  {trend}
                </div>
              )}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );

  if (tooltipText) {
    return (
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        animate="visible"
        whileHover="hover"
      >
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <motion.div variants={cardHover} initial="rest" animate="rest" whileHover="hover">
                {content}
              </motion.div>
            </TooltipTrigger>
            <TooltipContent>
              <p>{tooltipText}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </motion.div>
    );
  }

  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      animate="visible"
      whileHover="hover"
    >
      <motion.div variants={cardHover} initial="rest" animate="rest" whileHover="hover">
        {content}
      </motion.div>
    </motion.div>
  );
}
