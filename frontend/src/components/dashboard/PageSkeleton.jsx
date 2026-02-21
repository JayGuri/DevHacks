import { Skeleton } from "@/components/ui/skeleton";

export default function PageSkeleton({ layout = "overview" }) {
  if (layout === "overview") {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-lg border border-border p-5">
              <Skeleton className="mb-2 h-3 w-20" />
              <Skeleton className="h-8 w-24" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="rounded-lg border border-border p-5">
              <Skeleton className="mb-4 h-6 w-32" />
              <Skeleton className="h-64 w-full" />
            </div>
          </div>
          <div className="space-y-6 text-sm">
            <div className="rounded-lg border border-border p-5">
              <Skeleton className="mb-4 h-6 w-32" />
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (layout === "project" || layout === "admin") {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-lg border border-border p-5">
              <Skeleton className="mb-2 h-3 w-20" />
              <Skeleton className="h-8 w-24" />
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-border p-5">
          <Skeleton className="mb-4 h-6 w-32" />
          <Skeleton className="h-72 w-full" />
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-border p-5">
             <Skeleton className="mb-4 h-6 w-32" />
             <Skeleton className="h-48 w-full" />
          </div>
          <div className="rounded-lg border border-border p-5">
             <Skeleton className="mb-4 h-6 w-32" />
             <Skeleton className="h-48 w-full" />
          </div>
        </div>
      </div>
    );
  }

  return null;
}
