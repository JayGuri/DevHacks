import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const modes = [
  { value: "simple", label: "Simple", tip: "Summary cards and key metrics" },
  { value: "detailed", label: "Detailed", tip: "Full tables, raw data and charts" },
];

export default function ViewToggle() {
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);

  return (
    <TooltipProvider delayDuration={300}>
      <div className="inline-flex overflow-hidden rounded-md border border-border">
        {modes.map((m) => (
          <Tooltip key={m.value}>
            <TooltipTrigger asChild>
              <button
                onClick={() => setViewMode(m.value)}
                className={cn(
                  "mono-data px-3 py-1.5 text-xs transition-colors duration-150",
                  viewMode === m.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-transparent text-muted-foreground hover:bg-accent"
                )}
              >
                {m.label}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>{m.tip}</p>
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
    </TooltipProvider>
  );
}
