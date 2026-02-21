import { motion } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function StatCard({
  label,
  value,
  icon: Icon,
  color,
  description,
  className,
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className={cn("h-full", className)}>
        <CardContent className="flex items-start gap-3 p-4">
          {Icon && (
            <div className="rounded-md bg-primary/10 p-2">
              <Icon size={18} className="text-primary" />
            </div>
          )}
          <div className="flex-1">
            <p className="metric-label text-muted-foreground">{label}</p>
            <p className={cn("metric-value mt-0.5", color)}>{value}</p>
            {description && (
              <p className="mt-1 text-xs text-muted-foreground">
                {description}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
