import { cn } from "@/lib/utils";
import { memo } from "react";

const RoleBadge = memo(({ role }) => {
  const isLead = role === "TEAM_LEAD";

  return (
    <span
      className={cn(
        "badge-custom",
        isLead
          ? "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/20"
          : "bg-muted text-muted-foreground border-border"
      )}
    >
      {isLead ? "Team Lead" : "Contributor"}
    </span>
  );
});

export default RoleBadge;
