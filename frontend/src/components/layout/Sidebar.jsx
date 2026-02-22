import {
  NavLink,
  useNavigate,
  useParams,
  useLocation,
  Link,
} from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard,
  User,
  Monitor,
  Layers,
  Users,
  UserPlus,
  LogOut,
  Plus,
  Server,
  Settings,
  ChevronRight,
  CreditCard,
  Send,
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
import { memo } from "react";

// ── Status dot color ────────────────────────────────────────────────
function getStatusDotColor(project, nodesByProject) {
  if (!project.isActive) return "bg-slate-400";
  const nodes = nodesByProject[project.id] || [];
  const hasBlocked = nodes.some((n) => n.isBlocked);
  if (hasBlocked) return "bg-rose-500";
  return "bg-emerald-500";
}

// ── Simple sidebar nav link ─────────────────────────────────────────
const SidebarLink = memo(
  ({ icon: Icon, label, to, badge, end = false, onClick }) => {
    return (
      <NavLink
        to={to}
        end={end}
        onClick={onClick}
        className={({ isActive }) =>
          cn(
            "group relative flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[13px] transition-all duration-200",
            isActive ?
              "text-primary font-semibold"
            : "text-muted-foreground hover:text-foreground",
          )
        }
        style={({ isActive }) =>
          isActive ?
            {
              background:
                "linear-gradient(90deg, hsl(var(--primary)/0.12) 0%, transparent 100%)",
            }
          : {}
        }
      >
        {({ isActive }) => (
          <>
            {isActive && (
              <motion.div
                layoutId="sidebar-active-indicator"
                className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
              />
            )}
            <Icon
              size={16}
              className={cn(
                "shrink-0 transition-colors",
                isActive ? "text-primary" : (
                  "text-muted-foreground group-hover:text-foreground"
                ),
              )}
            />
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
  },
);

// ── Section label ───────────────────────────────────────────────────
const SectionLabel = memo(({ children }) => (
  <div className="flex items-center gap-2 px-3 pb-1.5 pt-5">
    <span className="metric-label text-[9px] text-muted-foreground/50 whitespace-nowrap">
      {children}
    </span>
    <div className="h-px w-full bg-muted/30" />
  </div>
));

// ── Project nav item with expandable sub-items ──────────────────────
const ProjectNavItem = memo(
  ({ project, currentUser, nodesByProject, onNavigate }) => {
    const { id: activeId } = useParams();
    const location = useLocation();
    const projectRoles = useStore((s) => s.projectRoles);

    const isOnThisProject =
      activeId === project.id &&
      (location.pathname.startsWith(`/dashboard/projects/${project.id}`) ||
        location.pathname.startsWith(`/admin/projects/${project.id}`));

    const isAdminRoute = location.pathname.startsWith("/admin/");
    const basePath =
      isAdminRoute ?
        `/admin/projects/${project.id}`
      : `/dashboard/projects/${project.id}`;

    const role = projectRoles[project.id]?.[currentUser?.id];
    const amLead = role === "lead";

    const dotColor = getStatusDotColor(project, nodesByProject);

    return (
      <div className="px-1">
        <NavLink
          to={`/dashboard/projects/${project.id}`}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all duration-200",
              isActive || isOnThisProject ?
                "text-primary font-semibold"
              : "text-muted-foreground hover:text-foreground",
            )
          }
          style={({ isActive }) =>
            isActive || isOnThisProject ?
              {
                background:
                  "linear-gradient(90deg, hsl(var(--primary)/0.08) 0%, transparent 100%)",
              }
            : {}
          }
        >
          {({ isActive }) => (
            <>
              {(isActive || isOnThisProject) && (
                <motion.div
                  layoutId="sidebar-active-indicator"
                  className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <span
                className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotColor)}
              />
              <span className="flex-1 truncate text-[13px]">
                {project.name}
              </span>
              <ChevronRight
                size={13}
                className={cn(
                  "shrink-0 text-muted-foreground/30 transition-transform duration-200",
                  isOnThisProject && "rotate-90 text-primary",
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
              <div className="ml-6 my-1 space-y-0.5 border-l border-border/60 pl-3">
                {/* Team leads see My Node; contributors go straight to My Workspace */}
                {amLead && (
                  <NavLink
                    to={`/dashboard/projects/${project.id}?tab=mynode`}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md py-1.5 px-2 text-[12px] transition-colors",
                        isActive ?
                          "bg-accent/50 font-medium text-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/30",
                      )
                    }
                  >
                    <User size={12} />
                    My Node
                  </NavLink>
                )}

                {/* Contributors → My Workspace; leads → Server Metrics */}
                {!amLead ?
                  <NavLink
                    to={`/dashboard/projects/${project.id}?tab=workspace`}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md py-1.5 px-2 text-[12px] transition-colors",
                        isActive ?
                          "bg-accent/50 font-medium text-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/30",
                      )
                    }
                  >
                    <Send size={12} />
                    My Workspace
                  </NavLink>
                : <NavLink
                    to={`${basePath}?tab=server`}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md py-1.5 px-2 text-[12px] transition-colors",
                        isActive ?
                          "bg-accent/50 font-medium text-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/30",
                      )
                    }
                  >
                    <Server size={12} />
                    Server Metrics
                  </NavLink>
                }

                {amLead && (
                  <NavLink
                    to={`${basePath}?tab=admin`}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md py-1.5 px-2 text-[12px] transition-colors",
                        isActive ?
                          "bg-accent/50 font-medium text-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent/30",
                      )
                    }
                  >
                    <Settings size={12} />
                    Project Admin
                  </NavLink>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  },
);

// ── SidebarContent (shared between Sidebar and MobileNav Sheet) ─────
export const SidebarContent = memo(({ onNavigate }) => {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();

  const nodesByProject = useStore((s) => s.nodesByProject);
  const extraProjects = useStore((s) => s.extraProjects);
  const joinRequests = useStore((s) => s.joinRequests);
  const userProjects = useStore((s) => s.userProjects);

  const isLead = currentUser?.role === "TEAM_LEAD";

  const managedProjectIds =
    isLead ?
      getAllProjects({ extraProjects })
        .filter((p) => p.createdBy === currentUser?.id)
        .map((p) => p.id)
    : [];

  const pendingRequestCount = joinRequests.filter(
    (r) => r.status === "pending" && managedProjectIds.includes(r.projectId),
  ).length;

  const joinedProjectIds = userProjects[currentUser?.id] || [];
  const joinedProjects = getAllProjects({ extraProjects }).filter((p) =>
    joinedProjectIds.includes(p.id),
  );

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex h-full flex-col bg-card">
      {/* Logo Section */}
      <div className="relative flex flex-col px-6 py-8">
        <div className="flex items-baseline gap-1">
          <span className="font-display text-3xl font-extrabold tracking-tighter text-primary">
            ARFL
          </span>
          <div className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
        </div>
        <span className="metric-label text-[9px] mt-1 opacity-60">
          Async Federated Learning
        </span>
        <div className="absolute bottom-4 left-6 right-12 h-[1px] bg-gradient-to-r from-primary/40 to-transparent animate-logo-pulse" />
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 space-y-1">
        <SectionLabel>Workspace</SectionLabel>
        <SidebarLink
          icon={LayoutDashboard}
          label="Overview"
          to="/dashboard/overview"
          end
          onClick={onNavigate}
        />

        {joinedProjects.length > 0 && (
          <>
            <SectionLabel>My Projects</SectionLabel>
            <div className="space-y-0.5">
              {joinedProjects.map((project) => (
                <ProjectNavItem
                  key={project.id}
                  project={project}
                  currentUser={currentUser}
                  nodesByProject={nodesByProject}
                  onNavigate={onNavigate}
                />
              ))}
            </div>
          </>
        )}

        <Link
          to="/dashboard/projects?tab=available"
          onClick={onNavigate}
          className="mx-3 mt-3 flex items-center gap-2 py-1 text-[11px] font-mono uppercase tracking-wider text-muted-foreground/60 transition-colors hover:text-primary group"
        >
          <Plus
            size={12}
            className="group-hover:rotate-90 transition-transform duration-300"
          />
          Join a project
        </Link>

        {isLead && (
          <>
            <SectionLabel>Admin Controls</SectionLabel>
            <SidebarLink
              icon={Monitor}
              label="System Overview"
              to="/admin/overview"
            />
            <SidebarLink
              icon={Layers}
              label="Manage Projects"
              to="/admin/projects"
            />
            <SidebarLink
              icon={UserPlus}
              label="Join Requests"
              to="/admin/requests"
              badge={pendingRequestCount}
            />
            <SidebarLink icon={Users} label="User Registry" to="/admin/users" />
            <SidebarLink
              icon={CreditCard}
              label="Billing"
              to="/admin/billing"
            />
          </>
        )}
      </nav>

      {/* User card */}
      <div className="mt-auto p-4">
        <div className="bg-muted/30 rounded-xl p-3 border border-border/40 flex items-center gap-3">
          <Avatar className="h-9 w-9 border border-border/60">
            <AvatarFallback className="text-[12px] bg-primary/5 text-primary font-bold">
              {getInitials(currentUser?.name)}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 overflow-hidden">
            <p className="truncate text-sm font-bold tracking-tight">
              {currentUser?.name}
            </p>
            <div className="scale-75 origin-left -mt-0.5">
              <RoleBadge role={currentUser?.role} />
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleLogout}
            className="h-8 w-8 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10"
          >
            <LogOut size={16} />
          </Button>
        </div>
      </div>
    </div>
  );
});

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 z-30 hidden h-screen w-64 flex-col border-r border-border/60 bg-card lg:flex">
      <SidebarContent />
    </aside>
  );
}

export { SidebarLink };
