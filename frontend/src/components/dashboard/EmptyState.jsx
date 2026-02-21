import { motion } from "framer-motion";
import { Inbox } from "lucide-react";

export default function EmptyState({ icon: Icon = Inbox, message }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center justify-center gap-3 py-12 text-center"
    >
      <Icon size={40} className="text-muted-foreground/50" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </motion.div>
  );
}
