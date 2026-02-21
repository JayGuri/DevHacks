import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  message,
  action,
}) {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center justify-center py-12 text-center"
    >
      <Icon size={48} className="text-muted-foreground/40" />
      {title && <p className="mt-4 text-lg font-medium">{title}</p>}
      {(description || message) && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {description || message}
        </p>
      )}
      {action && (
        <Button
          variant="outline"
          className="mt-6"
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
}
