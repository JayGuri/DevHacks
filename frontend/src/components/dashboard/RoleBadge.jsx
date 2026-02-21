import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export default function RoleBadge({ role }) {
  const isLead = role === "TEAM_LEAD";

  return (
    <Badge
      variant="outline"
      className={cn(
        isLead
          ? "border-cyan-500 text-cyan-600 dark:text-cyan-400"
          : "border-border text-muted-foreground"
      )}
    >
      {isLead ? "Team Lead" : "Contributor"}
    </Badge>
  );
}
