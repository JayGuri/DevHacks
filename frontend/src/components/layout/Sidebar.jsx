import { NavLink, useNavigate, useParams, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard, FolderOpen, User, Monitor, Layers,
  Users, UserPlus, LogOut, Hash, ArrowRight, Crown,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { getInitials, cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { getAllProjects, getUserProjectRole, getPendingRequests, getUserManagedProjects, getUserJoinedProjects, isProjectLead } from "@/lib/projectUtils";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
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

function SidebarLink({ icon: Icon, label, to, badge }) {
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
      <span className="flex-1">{label}</span>
      {badge != null && badge > 0 && (
        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 text-[10px] font-bold text-white">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </NavLink>
  );
}

function ProjectContext({ currentUser }) {
  const { id } = useParams();
  const location = useLocation();
  const store = useStore();

  const isProjectRoute =
    location.pathname.startsWith("/dashboard/projects/") ||
    location.pathname.startsWith("/admin/projects/");

  if (!isProjectRoute || !id) return null;

  const allProjects = getAllProjects(store);
  const project = allProjects.find((p) => p.id === id);
  if (!project) return null;

  const role = getUserProjectRole(currentUser?.id, id, store);
  const roleLabel = role === "lead" ? "TEAM_LEAD" : "CONTRIBUTOR";

  const isAdminRoute = location.pathname.startsWith("/admin/");
  const basePath = isAdminRoute ? `/admin/projects/${id}` : `/dashboard/projects/${id}`;

  return (
    <AnimatePresence>
      <motion.div
        key="project-ctx"
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: "auto", opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="overflow-hidden"
      >
        <Separator className="my-2" />
        <div className="px-4 py-2">
          <p className="metric-label text-muted-foreground">Current Project</p>
          <p className="mt-1 truncate text-sm font-medium">{project.name}</p>
          <div className="mt-1">
            <RoleBadge role={roleLabel} />
          </div>
          <div className="mt-2 space-y-1">
            <NavLink
              to={basePath}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              <Hash size={12} />
              {role === "lead" ? "Server View" : "My Node"}
              <ArrowRight size={10} />
            </NavLink>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

export default function Sidebar() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();
  const store = useStore();
  const isLead = currentUser?.role === "TEAM_LEAD";

  const pendingRequestCount = isLead
    ? getUserManagedProjects(currentUser?.id, store).reduce(
        (sum, p) => sum + getPendingRequests(p.id, store).length,
        0
      )
    : 0;

  const joinedProjects = getUserJoinedProjects(currentUser?.id, store);
  const ledProjects = joinedProjects.filter((p) =>
    isProjectLead(currentUser?.id, p.id, store)
  );

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <aside className="fixed left-0 top-0 z-30 hidden h-screen w-60 flex-col border-r border-border bg-card lg:flex">
      {/* Logo */}
      <div className="flex items-center gap-2 px-6 py-5">
        <span className="font-display text-2xl font-bold text-primary">ARFL</span>
        <span className="h-2 w-2 rounded-full bg-primary" />
      </div>
      <Separator />

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {CONTRIBUTOR_NAV.map((item) => (
          <SidebarLink key={item.to} {...item} />
        ))}

        {ledProjects.length > 0 && (
          <>
            <Separator className="my-3" />
            <p className="metric-label px-4 pb-1 text-muted-foreground">Projects I Lead</p>
            {ledProjects.map((p) => (
              <SidebarLink key={`lead-${p.id}`} icon={Crown} label={p.name} to={`/dashboard/projects/${p.id}`} />
            ))}
          </>
        )}

        {isLead && (
          <>
            <Separator className="my-3" />
            <p className="metric-label px-4 pb-1 text-muted-foreground">Admin</p>
            {ADMIN_NAV.map((item) => (
              <SidebarLink key={item.to} {...item} />
            ))}
            <SidebarLink
              icon={UserPlus}
              label="Join Requests"
              to="/admin/requests"
              badge={pendingRequestCount}
            />
          </>
        )}

        <ProjectContext currentUser={currentUser} />
      </nav>

      {/* User section */}
      <Separator />
      <div className="flex items-center gap-3 px-4 py-4">
        <Avatar className="h-8 w-8">
          <AvatarFallback className="text-xs">{getInitials(currentUser?.name)}</AvatarFallback>
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
