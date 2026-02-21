import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { memo } from "react";
import { cn } from "@/lib/utils";

const EmptyState = memo(({
  icon: Icon = Inbox,
  title,
  description,
  message,
  action,
  className,
}) => {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={cn(
        "flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-border/60 empty-state-bg min-h-[300px]",
        className
      )}
    >
      <div className="relative">
        <div className="absolute inset-0 blur-2xl bg-primary/5 rounded-full" />
        <Icon size={64} className="text-muted-foreground/30 relative" strokeWidth={1.5} />
      </div>
      
      {title && <h3 className="mt-6 text-xl font-display font-bold tracking-tight">{title}</h3>}
      {(description || message) && (
        <p className="mt-2 max-w-sm text-sm text-muted-foreground leading-relaxed">
          {description || message}
        </p>
      )}
      
      {action && (
        <Button
          variant="outline"
          className="mt-8 rounded-full px-6 btn-primary-glow"
          onClick={
            action.onClick
              ? action.onClick
              : action.href
                ? () => navigate(action.href)
                : undefined
          }
        >
          {action.label}
        </Button>
      )}
    </motion.div>
  );
});

export default EmptyState;
