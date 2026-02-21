import { useState, useMemo, useEffect } from "react";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { useStore } from "@/lib/store";
import { MOCK_USERS } from "@/lib/mockData";
import { USE_MOCK } from "@/lib/config";
import { apiListUsers, apiUpdateUserRole, apiListProjects } from "@/lib/api";
import { getAllProjects } from "@/lib/projectUtils";
import AppLayout from "@/components/layout/AppLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AdminUsers() {
  const store = useStore();
  const viewMode = store.viewMode;
  const nodesByProject = store.nodesByProject;
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState("");

  // Fetch users and projects on mount
  useEffect(() => {
    if (!USE_MOCK) {
      apiListUsers()
        .then((data) => setUsers(data))
        .catch((err) => {
          console.error("Failed to fetch users:", err);
          setUsers([]);
        });
      apiListProjects()
        .then((data) => store.setProjects(data))
        .catch(() => {});
    } else {
      setUsers(MOCK_USERS);
    }
  }, []);

  const filtered = useMemo(
    () =>
      users.filter(
        (u) =>
          u.name.toLowerCase().includes(search.toLowerCase()) ||
          u.email.toLowerCase().includes(search.toLowerCase()),
      ),
    [users, search],
  );

  const allProjectsList = getAllProjects(store);

  function projectCount(userId) {
    return allProjectsList.filter((p) =>
      p.members?.some((m) => m.userId === userId),
    ).length;
  }

  function userAvgTrust(userId) {
    let sum = 0,
      count = 0;
    allProjectsList.forEach((p) => {
      const member = p.members?.find((m) => m.userId === userId);
      if (!member) return;
      const nodes = nodesByProject[p.id] || [];
      const node = nodes.find((n) => n.displayId === member.nodeId);
      if (node) {
        sum += node.trust;
        count++;
      }
    });
    return count > 0 ? ((sum / count) * 100).toFixed(1) + "%" : "—";
  }

  function userTotalRounds(userId) {
    let total = 0;
    allProjectsList.forEach((p) => {
      const member = p.members?.find((m) => m.userId === userId);
      if (!member) return;
      const nodes = nodesByProject[p.id] || [];
      const node = nodes.find((n) => n.displayId === member.nodeId);
      if (node) total += node.roundsContributed || 0;
    });
    return total;
  }

  async function handleRoleChange(userId, newRole) {
    if (!USE_MOCK) {
      try {
        await apiUpdateUserRole(userId, newRole);
      } catch (err) {
        toast.error(err.message || "Failed to update role");
        return;
      }
    }
    setUsers((prev) =>
      prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)),
    );
    toast.success("Role updated");
  }

  return (
    <AppLayout title="Users">
      <div className="mb-4 relative sm:max-w-xs">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          placeholder="Search by name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Projects</TableHead>
              {viewMode === "detailed" && <TableHead>Avg Trust</TableHead>}
              {viewMode === "detailed" && <TableHead>Total Rounds</TableHead>}
              <TableHead>Joined</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell className="mono-data text-xs">{u.email}</TableCell>
                <TableCell>
                  <Select
                    value={u.role}
                    onValueChange={(v) => handleRoleChange(u.id, v)}
                  >
                    <SelectTrigger className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="TEAM_LEAD">Team Lead</SelectItem>
                      <SelectItem value="CONTRIBUTOR">Contributor</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{projectCount(u.id)}</Badge>
                </TableCell>
                {viewMode === "detailed" && (
                  <TableCell className="mono-data text-xs">
                    {userAvgTrust(u.id)}
                  </TableCell>
                )}
                {viewMode === "detailed" && (
                  <TableCell className="mono-data text-xs">
                    {userTotalRounds(u.id)}
                  </TableCell>
                )}
                <TableCell className="text-xs text-muted-foreground">
                  {u.createdAt}
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => toast.info("Profile view coming soon")}
                  >
                    View Profile
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </AppLayout>
  );
}
