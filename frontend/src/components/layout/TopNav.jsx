import { motion, AnimatePresence } from "framer-motion";
import { useNavigate, Link } from "react-router-dom";
import { useTheme } from "next-themes";
import {
  Sun, Moon, ChevronRight, LogOut, Bell,
  UserPlus, CheckCircle, XCircle, AlertTriangle, Settings,
  Home, Command,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useAuth } from "@/contexts/AuthContext";
import { getInitials, cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { getUserManagedProjects } from "@/lib/projectUtils";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import ViewToggle from "@/components/dashboard/ViewToggle";

const NOTIF_ICONS = {
  join_request: UserPlus,
  request_approved: CheckCircle,
  request_rejected: XCircle,
  alert: AlertTriangle,
  node_blocked: AlertTriangle,
  config: Settings,
};

export default function TopNav({ breadcrumbs = [] }) {
  const { currentUser, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const store = useStore();
  const notifications = store.notifications;
  const markNotificationRead = store.markNotificationRead;
  const markAllRead = store.markAllRead;

  const isLead = currentUser?.role === "TEAM_LEAD";

  const managedProjectIds = isLead
    ? getUserManagedProjects(currentUser?.id, store).map((p) => p.id)
    : [];

  const myNotifications = notifications.filter((n) => {
    if (isLead) {
      if (n.type === "join_request" && managedProjectIds.includes(n.projectId)) return true;
      if (["alert", "node_blocked", "config"].includes(n.type)) return true;
    }
    if (n.type === "request_approved" && n.targetUserId === currentUser?.id) return true;
    if (n.type === "request_rejected" && n.targetUserId === currentUser?.id) return true;
    if (n.toUserId === currentUser?.id) return true;
    return false;
  });

  const unreadCount = myNotifications.filter((n) => !n.read).length;

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="fixed left-0 right-0 top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur-sm lg:left-60 lg:px-6">
      {/* Left: breadcrumbs with Home icon */}
      <nav className="flex items-center gap-1 text-sm min-w-0">
        <Link
          to="/dashboard/overview"
          className="flex shrink-0 items-center text-muted-foreground transition-colors hover:text-foreground"
          title="Home"
        >
          <Home size={14} />
        </Link>

        {breadcrumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1 min-w-0">
            <ChevronRight size={13} className="shrink-0 text-muted-foreground/50" />
            {crumb.href ? (
              <Link
                to={crumb.href}
                className="truncate text-muted-foreground transition-colors hover:text-foreground"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className="truncate font-medium text-foreground">
                {crumb.label}
              </span>
            )}
          </span>
        ))}
      </nav>

      {/* Right: Ctrl+K hint, view toggle, notifications, theme, avatar */}
      <div className="flex shrink-0 items-center gap-1.5">

        {/* Ctrl+K hint */}
        <button
          className="hidden items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent/50 sm:flex"
          onClick={() => document.dispatchEvent(new CustomEvent("open-command-palette"))}
          title="Open command palette"
        >
          <Command size={11} />
          <span>K</span>
        </button>

        <ViewToggle />

        {/* Notification bell */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="relative">
              <Bell size={16} />
              <AnimatePresence>
                {unreadCount > 0 && (
                  <motion.span
                    key={unreadCount}
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: [1, 1.4, 1], opacity: 1 }}
                    exit={{ scale: 0.8, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                    className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white"
                  >
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </motion.span>
                )}
              </AnimatePresence>
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 p-0">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="metric-label text-muted-foreground">Notifications</span>
              {unreadCount > 0 && (
                <button onClick={markAllRead} className="text-xs text-primary hover:underline">
                  Mark all read
                </button>
              )}
            </div>
            <div className="max-h-80 overflow-y-auto">
              {myNotifications.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">No notifications</p>
              ) : (
                myNotifications.map((n) => {
                  const Icon = NOTIF_ICONS[n.type] || Bell;
                  return (
                    <button
                      key={n.id}
                      className={cn(
                        "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50",
                        !n.read && "bg-muted/50"
                      )}
                      onClick={() => markNotificationRead(n.id)}
                    >
                      <Icon size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm leading-snug">{n.message}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {n.createdAt ? formatDistanceToNow(new Date(n.createdAt), { addSuffix: true }) : ""}
                        </p>
                      </div>
                      {!n.read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />}
                    </button>
                  );
                })
              )}
            </div>
            <div className="border-t border-border px-4 py-2">
              <button
                className="text-xs text-primary hover:underline"
                onClick={() => navigate(isLead ? "/admin/requests" : "/dashboard/projects")}
              >
                {isLead ? "View join requests" : "View my projects"}
              </button>
            </div>
          </PopoverContent>
        </Popover>

        <Button variant="ghost" size="icon" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="rounded-full">
              <Avatar className="h-8 w-8">
                <AvatarFallback className="text-xs">{getInitials(currentUser?.name)}</AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <p className="text-sm font-medium">{currentUser?.name}</p>
              <p className="text-xs text-muted-foreground">{currentUser?.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout}>
              <LogOut size={14} />
              Sign Out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
