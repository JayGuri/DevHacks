import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  FolderOpen,
  User,
  Monitor,
  Layers,
  Users,
  LogOut,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { getInitials, cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import RoleBadge from "@/components/dashboard/RoleBadge";

const CONTRIBUTOR_NAV = [
  { icon: LayoutDashboard, label: "Overview", to: "/dashboard/overview" },
  { icon: FolderOpen, label: "My Projects", to: "/dashboard/projects" },
  { icon: User, label: "Profile", to: "/dashboard/profile" },
];

const ADMIN_NAV = [
  { icon: Monitor, label: "System", to: "/admin/overview" },
  { icon: Layers, label: "All Projects", to: "/admin/projects" },
  { icon: Users, label: "Users", to: "/admin/users" },
];

function SidebarLink({ icon: Icon, label, to }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 rounded-sm px-4 py-2.5 text-sm transition-colors",
          isActive
            ? "border-l-2 border-primary bg-primary/10 font-medium text-primary"
            : "text-muted-foreground hover:bg-accent/50"
        )
      }
    >
      <Icon size={16} />
      {label}
    </NavLink>
  );
}

export default function Sidebar() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();
  const isLead = currentUser?.role === "TEAM_LEAD";

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <aside className="fixed left-0 top-0 z-30 hidden h-screen w-60 flex-col border-r border-border bg-card lg:flex">
      {/* Logo */}
      <div className="flex items-center gap-2 px-6 py-5">
        <span className="font-display text-2xl font-bold text-primary">
          ARFL
        </span>
        <span className="h-2 w-2 rounded-full bg-primary" />
      </div>
      <Separator />

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {CONTRIBUTOR_NAV.map((item) => (
          <SidebarLink key={item.to} {...item} />
        ))}

        {isLead && (
          <>
            <Separator className="my-3" />
            <p className="metric-label px-4 pb-1 text-muted-foreground">
              Admin
            </p>
            {ADMIN_NAV.map((item) => (
              <SidebarLink key={item.to} {...item} />
            ))}
          </>
        )}
      </nav>

      {/* User section */}
      <Separator />
      <div className="flex items-center gap-3 px-4 py-4">
        <Avatar className="h-8 w-8">
          <AvatarFallback className="text-xs">
            {getInitials(currentUser?.name)}
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 overflow-hidden">
          <p className="truncate text-sm font-medium">{currentUser?.name}</p>
          <RoleBadge role={currentUser?.role} />
        </div>
        <Button variant="ghost" size="icon" onClick={handleLogout}>
          <LogOut size={16} />
        </Button>
      </div>
    </aside>
  );
}

export { CONTRIBUTOR_NAV, ADMIN_NAV, SidebarLink };
