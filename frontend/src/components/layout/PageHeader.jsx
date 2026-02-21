import { cn } from "@/lib/utils";

/**
 * Rich page header component.
 *
 * Props:
 *   title     – string, main heading
 *   subtitle  – string, secondary description line
 *   icon      – ReactNode, optional icon shown left of title
 *   badge     – ReactNode, optional badge shown after title
 *   actions   – ReactNode[], optional action buttons in top-right
 */
export default function PageHeader({ title, subtitle, icon, badge, actions }) {
  return (
    <div className="flex items-start justify-between border-b border-border bg-card px-6 py-4">
      {/* Left: icon + title + badge + subtitle */}
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <div className="mt-0.5 shrink-0 rounded-md bg-primary/10 p-2 text-primary">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className={cn("font-display text-2xl font-semibold leading-tight truncate")}>
              {title}
            </h1>
            {badge}
          </div>
          {subtitle && (
            <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
      </div>

      {/* Right: actions */}
      {actions && actions.length > 0 && (
        <div className="ml-4 flex shrink-0 items-center gap-2">
          {actions}
        </div>
      )}
    </div>
  );
}
