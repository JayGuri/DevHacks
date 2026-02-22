import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  FolderOpen,
  User,
  Monitor,
  Layers,
  ShieldCheck,
  Sun,
  Moon,
  LogOut,
  ArrowRight,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import {
  getUserJoinedProjects,
  getUserManagedProjects,
} from "@/lib/projectUtils";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

export default function CommandPalette({ open, onOpenChange }) {
  const { currentUser, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const store = useStore();

  const isLead = currentUser?.role === "TEAM_LEAD";
  const joinedProjects = getUserJoinedProjects(currentUser?.id, store);
  const managedProjects =
    isLead ? getUserManagedProjects(currentUser?.id, store) : [];

  // Merge joined + managed, deduplicate
  const allMyProjects = [
    ...joinedProjects,
    ...managedProjects.filter(
      (p) => !joinedProjects.some((j) => j.id === p.id),
    ),
  ];

  function run(fn) {
    onOpenChange(false);
    // Small delay so the dialog closes before navigation/action
    setTimeout(fn, 80);
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type a command or search…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        {/* Navigation */}
        <CommandGroup heading="Navigation">
          <CommandItem
            onSelect={() => run(() => navigate("/dashboard/overview"))}
          >
            <LayoutDashboard size={14} className="mr-2 text-muted-foreground" />
            Go to Overview
          </CommandItem>
          <CommandItem
            onSelect={() => run(() => navigate("/dashboard/projects"))}
          >
            <FolderOpen size={14} className="mr-2 text-muted-foreground" />
            Go to Projects
          </CommandItem>
          {isLead && (
            <>
              <CommandItem
                onSelect={() => run(() => navigate("/admin/overview"))}
              >
                <Monitor size={14} className="mr-2 text-muted-foreground" />
                Go to System
              </CommandItem>
              <CommandItem
                onSelect={() => run(() => navigate("/admin/projects"))}
              >
                <Layers size={14} className="mr-2 text-muted-foreground" />
                Go to All Projects
              </CommandItem>
              <CommandItem
                onSelect={() => run(() => navigate("/admin/security"))}
              >
                <ShieldCheck size={14} className="mr-2 text-muted-foreground" />
                Go to Security
              </CommandItem>
            </>
          )}
        </CommandGroup>

        {/* Projects */}
        {allMyProjects.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Projects">
              {allMyProjects.map((p) => (
                <CommandItem
                  key={p.id}
                  onSelect={() =>
                    run(() => navigate(`/dashboard/projects/${p.id}`))
                  }
                >
                  <ArrowRight
                    size={14}
                    className="mr-2 text-muted-foreground"
                  />
                  Open {p.name}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {/* Actions */}
        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() =>
              run(() => setTheme(theme === "dark" ? "light" : "dark"))
            }
          >
            {theme === "dark" ?
              <Sun size={14} className="mr-2 text-muted-foreground" />
            : <Moon size={14} className="mr-2 text-muted-foreground" />}
            Toggle Dark Mode
          </CommandItem>
          <CommandItem
            onSelect={() =>
              run(() => {
                logout();
                navigate("/login");
              })
            }
          >
            <LogOut size={14} className="mr-2 text-muted-foreground" />
            Sign Out
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
