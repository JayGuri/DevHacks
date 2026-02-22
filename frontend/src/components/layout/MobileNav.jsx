import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Home, FolderOpen, UserPlus, MoreHorizontal } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { getUserManagedProjects, getPendingRequests } from "@/lib/projectUtils";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SidebarContent } from "@/components/layout/Sidebar";

function TabLink({ icon: Icon, label, to, badge }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "relative flex flex-col items-center gap-1 px-2 py-1.5 text-[10px] font-medium transition-colors",
          isActive ? "text-primary" : "text-muted-foreground",
        )
      }
    >
      <span className="relative">
        <Icon size={20} strokeWidth={1.75} />
        {badge > 0 && (
          <span className="absolute -right-1.5 -top-1 flex h-4 min-w-[14px] items-center justify-center rounded-full bg-rose-500 px-0.5 text-[9px] font-bold text-white">
            {badge > 9 ? "9+" : badge}
          </span>
        )}
      </span>
      {label}
    </NavLink>
  );
}

export default function MobileNav() {
  const { currentUser } = useAuth();
  const store = useStore();
  const [open, setOpen] = useState(false);
  const isLead = currentUser?.role === "TEAM_LEAD";

  const pendingRequestCount =
    isLead ?
      getUserManagedProjects(currentUser?.id, store).reduce(
        (sum, p) => sum + getPendingRequests(p.id, store).length,
        0,
      )
    : 0;

  return (
    <>
      {/* Bottom tab bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-stretch justify-around border-t border-border bg-card px-1 lg:hidden">
        <TabLink icon={Home} label="Home" to="/dashboard/overview" />
        <TabLink icon={FolderOpen} label="Projects" to="/dashboard/projects" />
        {isLead && (
          <TabLink
            icon={UserPlus}
            label="Requests"
            to="/admin/requests"
            badge={pendingRequestCount}
          />
        )}
        <button
          onClick={() => setOpen(true)}
          className="flex flex-col items-center gap-1 px-2 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors"
        >
          <MoreHorizontal size={20} strokeWidth={1.75} />
          More
        </button>
      </nav>

      {/* Sheet with full sidebar content */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 p-0">
          {/* Visually hidden title for accessibility */}
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation Menu</SheetTitle>
          </SheetHeader>
          <SidebarContent onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
    </>
  );
}
