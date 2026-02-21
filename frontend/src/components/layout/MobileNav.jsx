import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Home, FolderOpen, User, Monitor, Menu, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { cn, getInitials } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import RoleBadge from "@/components/dashboard/RoleBadge";
import {
  CONTRIBUTOR_NAV,
  ADMIN_NAV,
  SidebarLink,
} from "@/components/layout/Sidebar";

function TabLink({ icon: Icon, label, to }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex flex-col items-center gap-0.5 text-[10px]",
          isActive ? "text-primary" : "text-muted-foreground"
        )
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  );
}

export default function MobileNav() {
  const { currentUser, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const isLead = currentUser?.role === "TEAM_LEAD";

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <>
      {/* Bottom tab bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-border bg-card px-2 py-2 lg:hidden">
        <TabLink icon={Home} label="Home" to="/dashboard/overview" />
        <TabLink icon={FolderOpen} label="Projects" to="/dashboard/projects" />
        <TabLink icon={User} label="Profile" to="/dashboard/profile" />
        {isLead && (
          <TabLink icon={Monitor} label="Admin" to="/admin/overview" />
        )}
        <button
          onClick={() => setOpen(true)}
          className="flex flex-col items-center gap-0.5 text-[10px] text-muted-foreground"
        >
          <Menu size={18} />
          Menu
        </button>
      </nav>

      {/* Sheet with full sidebar nav */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="px-6 pt-6">
            <SheetTitle className="font-display text-2xl text-primary">
              ARFL
            </SheetTitle>
          </SheetHeader>

          <nav
            className="flex-1 space-y-1 px-3 py-4"
            onClick={() => setOpen(false)}
          >
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

          <Separator />
          <div className="flex items-center gap-3 px-4 py-4">
            <Avatar className="h-8 w-8">
              <AvatarFallback className="text-xs">
                {getInitials(currentUser?.name)}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-sm font-medium">
                {currentUser?.name}
              </p>
              <RoleBadge role={currentUser?.role} />
            </div>
            <Button variant="ghost" size="icon" onClick={handleLogout}>
              <LogOut size={16} />
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
