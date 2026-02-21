import { NavLink, useNavigate, useParams, useLocation, Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard, User, Monitor, Layers,
  Users, UserPlus, LogOut, ShieldCheck, Plus,
  Server, Settings, ChevronRight,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { getInitials, cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import {
  getAllProjects,
  getUserProjectRole,
  getPendingRequests,
  getUserManagedProjects,
  getUserJoinedProjects,
  isProjectLead,
} from "@/lib/projectUtils";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import RoleBadge from "@/components/dashboard/RoleBadge";

// ── Status dot color ────────────────────────────────────────────────
function getStatusDotColor(project, store) {
  if (!project.isActive) return "bg-slate-400";
  const nodes = store.nodesByProject?.[project.id] || [];
  const hasBlocked = nodes.some((n) => n.isBlocked);
  if (hasBlocked) return "bg-rose-500";
  // "paused" concept — treat archived/inactive as amber if live but paused
  // For demo: paused = not active but still exists
  return "bg-emerald-500";
}

// ── Simple sidebar nav link ─────────────────────────────────────────
function SidebarLink({ icon: Icon, label, to, badge, end = false, onClick }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-primary/10 font-medium text-primary"
            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.div
              layoutId="sidebar-active-indicator"
              className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary"
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
            />
          )}
          <Icon size={15} className="shrink-0" />
          <span className="flex-1 truncate">{label}</span>
          {badge != null && badge > 0 && (
            <span className="flex h-4.5 min-w-[18px] items-center justify-center rounded-full bg-rose-500 px-1.5 text-[10px] font-bold text-white">
              {badge > 9 ? "9+" : badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

// ── Section label ───────────────────────────────────────────────────
function SectionLabel({ children }) {
  return (
    <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
      {children}
    </p>
  );
}

// ── Project nav item with expandable sub-items ──────────────────────
function ProjectNavItem({ project, currentUser, store, onNavigate }) {
  const { id: activeId } = useParams();
  const location = useLocation();

  const isOnThisProject =
    activeId === project.id &&
    (location.pathname.startsWith(`/dashboard/projects/${project.id}`) ||
      location.pathname.startsWith(`/admin/projects/${project.id}`));

  const isAdminRoute = location.pathname.startsWith("/admin/");
  const basePath = isAdminRoute
    ? `/admin/projects/${project.id}`
    : `/dashboard/projects/${project.id}`;

  const role = getUserProjectRole(currentUser?.id, project.id, store);
  const amLead = role === "lead";

  const dotColor = getStatusDotColor(project, store);

  return (
    <div>
      <NavLink
        to={`/dashboard/projects/${project.id}`}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            "relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
            isActive || isOnThisProject
              ? "bg-primary/10 font-medium text-primary"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
          )
        }
      >
        {({ isActive }) => (
          <>
            {(isActive || isOnThisProject) && (
              <motion.div
                layoutId="sidebar-active-indicator"
                className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
              />
            )}
            <span className={cn("h-2 w-2 shrink-0 rounded-full", dotColor)} />
            <span className="flex-1 truncate text-[13px]">{project.name}</span>
            <ChevronRight
              size={13}
              className={cn(
                "shrink-0 text-muted-foreground/50 transition-transform",
                isOnThisProject && "rotate-90"
              )}
            />
          </>
        )}
      </NavLink>

      <AnimatePresence initial={false}>
        {isOnThisProject && (
          <motion.div
            key={`sub-${project.id}`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="ml-6 mt-0.5 space-y-0.5 border-l-2 border-border pl-3">
              {!amLead && (
                <NavLink
                  to={`/dashboard/projects/${project.id}?tab=mynode`}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2 rounded py-1.5 text-xs transition-colors",
                      isActive
                        ? "font-medium text-primary"
                        : "text-muted-foreground hover:text-foreground"
                    )
                  }
                >
                  <User size={11} />
                  My Node
                </NavLink>
              )}
              <NavLink
                to={`${basePath}?tab=server`}
                onClick={onNavigate}
                className="flex items-center gap-2 rounded py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                <Server size={11} />
                Server Metrics
              </NavLink>
              {amLead && (
                <NavLink
                  to={`${basePath}?tab=admin`}
                  onClick={onNavigate}
                  className="flex items-center gap-2 rounded py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <Settings size={11} />
                  Project Admin
                </NavLink>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── SidebarContent (shared between Sidebar and MobileNav Sheet) ─────
export function SidebarContent({ onNavigate }) {
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

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex flex-col px-5 py-5">
        <span className="font-display text-2xl font-bold text-primary">ARFL</span>
        <span className="text-[10px] text-muted-foreground/70 tracking-wide">
          Async Federated Learning
        </span>
      </div>
      <Separator />

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {/* WORKSPACE */}
        <SectionLabel>Workspace</SectionLabel>
        <SidebarLink
          icon={LayoutDashboard}
          label="Overview"
          to="/dashboard/overview"
          end
          onClick={onNavigate}
        />

        {/* MY PROJECTS */}
        {joinedProjects.length > 0 && (
          <>
            <SectionLabel>My Projects</SectionLabel>
            <div className="space-y-0.5">
              {joinedProjects.map((project) => (
                <ProjectNavItem
                  key={project.id}
                  project={project}
                  currentUser={currentUser}
                  store={store}
                  onNavigate={onNavigate}
                />
              ))}
            </div>
            <Link
              to="/dashboard/projects?tab=available"
              onClick={onNavigate}
              className="mt-2 flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
            >
              <Plus size={12} />
              Join a project
            </Link>
          </>
        )}

        {/* TOOLS */}
        <SectionLabel>Tools</SectionLabel>
        <SidebarLink icon={User} label="Profile" to="/dashboard/profile" />

        {/* ADMIN */}
        {isLead && (
          <>
            <Separator className="my-3" />
            <SectionLabel>Admin</SectionLabel>
            <SidebarLink icon={Monitor} label="System" to="/admin/overview" />
            <SidebarLink icon={Layers} label="All Projects" to="/admin/projects" />
            <SidebarLink
              icon={UserPlus}
              label="Join Requests"
              to="/admin/requests"
              badge={pendingRequestCount}
            />
            <SidebarLink icon={Users} label="Users" to="/admin/users" />
            <SidebarLink icon={ShieldCheck} label="Security" to="/admin/security" />
          </>
        )}
      </nav>

      {/* User card */}
      <Separator />
      <div className="flex items-center gap-3 px-4 py-3">
        <Avatar className="h-8 w-8">
          <AvatarFallback className="text-xs">
            {getInitials(currentUser?.name)}
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 overflow-hidden">
          <p className="truncate text-sm font-medium">{currentUser?.name}</p>
          <RoleBadge role={currentUser?.role} />
        </div>
        <Button variant="ghost" size="icon" onClick={handleLogout} title="Sign out">
          <LogOut size={15} />
        </Button>
      </div>
    </div>
  );
}

// ── Default export: desktop sidebar shell ───────────────────────────
export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 z-30 hidden h-screen w-60 flex-col border-r border-border bg-card lg:flex">
      <SidebarContent />
    </aside>
  );
}

// Legacy named exports for backward compat (MobileNav imports these)
export { SidebarLink };
