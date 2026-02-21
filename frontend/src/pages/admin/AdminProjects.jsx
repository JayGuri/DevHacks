import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Search } from "lucide-react";
import { useStore } from "@/lib/store";
import { MOCK_PROJECTS } from "@/lib/mockData";
import { formatPercent, formatEpsilon } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import NewProjectDialog from "@/components/admin/NewProjectDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export default function AdminProjects() {
  const navigate = useNavigate();
  const viewMode = useStore((s) => s.viewMode);
  const nodesByProject = useStore((s) => s.nodesByProject);
  const roundsByProject = useStore((s) => s.roundsByProject);

  const [projects, setProjects] = useState(MOCK_PROJECTS);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);

  const filtered = useMemo(
    () =>
      projects.filter((p) =>
        p.name.toLowerCase().includes(search.toLowerCase())
      ),
    [projects, search]
  );

  function latestAccuracy(pid) {
    const rounds = roundsByProject[pid] || [];
    return rounds[rounds.length - 1]?.globalAccuracy || 0;
  }

  function nodeCounts(pid) {
    const nodes = nodesByProject[pid] || [];
    const byz = nodes.filter(
      (n) => n.isByzantine || n.status === "BYZANTINE"
    ).length;
    return { byz, honest: nodes.length - byz };
  }

  function handleCreate(data) {
    const id = `p${Date.now()}`;
    const newProject = {
      id,
      name: data.name,
      description: data.description || "",
      createdBy: "u1",
      createdAt: new Date().toISOString().split("T")[0],
      isActive: true,
      config: {
        numClients: data.numClients,
        byzantineFraction: data.byzantineFraction,
        attackType: data.attackType,
        aggregationMethod: data.aggregationMethod,
        numRounds: data.numRounds,
        dirichletAlpha: data.dirichletAlpha,
        useDifferentialPrivacy: data.useDifferentialPrivacy,
        dpNoiseMultiplier: data.dpNoiseMultiplier,
        dpMaxGradNorm: 1.0,
        sabdAlpha: data.sabdAlpha,
        localEpochs: 3,
      },
      members: [
        {
          userId: "u1",
          userName: "Alex Morgan",
          nodeId: "NODE_A1",
          role: "lead",
          joinedAt: new Date().toISOString().split("T")[0],
        },
      ],
    };
    setProjects((prev) => [...prev, newProject]);
    setDialogOpen(false);
    toast.success("Project created");
  }

  function handleArchive(pid) {
    setProjects((prev) =>
      prev.map((p) => (p.id === pid ? { ...p, isActive: false } : p))
    );
    toast.success("Project archived");
  }

  return (
    <AppLayout title="All Projects">
      {/* Header */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 sm:max-w-xs">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            placeholder="Search projects…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus size={14} className="mr-1" /> New Project
        </Button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Members</TableHead>
              <TableHead>Accuracy</TableHead>
              <TableHead>Nodes B/H</TableHead>
              {viewMode === "detailed" && <TableHead>Attack</TableHead>}
              {viewMode === "detailed" && <TableHead>Aggregator</TableHead>}
              {viewMode === "detailed" && <TableHead>ε Spent</TableHead>}
              <TableHead>Created</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((p) => {
              const { byz, honest } = nodeCounts(p.id);
              return (
                <TableRow
                  key={p.id}
                  className={cn(!p.isActive && "opacity-50")}
                >
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell>{p.members.length}</TableCell>
                  <TableCell className="mono-data">
                    {formatPercent(latestAccuracy(p.id))}
                  </TableCell>
                  <TableCell className="mono-data">
                    <span className="text-rose-500">{byz}</span>/
                    <span className="text-emerald-500">{honest}</span>
                  </TableCell>
                  {viewMode === "detailed" && (
                    <TableCell className="text-xs">{p.config?.attackType?.replace(/_/g, " ") || "—"}</TableCell>
                  )}
                  {viewMode === "detailed" && (
                    <TableCell className="text-xs">{p.config?.aggregationMethod?.replace(/_/g, " ") || "—"}</TableCell>
                  )}
                  {viewMode === "detailed" && (
                    <TableCell className="mono-data text-xs">
                      {((roundsByProject[p.id] || []).slice(-1)[0]?.epsilonSpent || 0).toFixed(2)}
                    </TableCell>
                  )}
                  <TableCell className="text-xs text-muted-foreground">
                    {p.createdAt}
                  </TableCell>
                  <TableCell>
                    {p.isActive ? (
                      <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                        Active
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-muted-foreground">
                        Archived
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/admin/projects/${p.id}`)}
                      >
                        View
                      </Button>
                      {p.isActive && (
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="ghost">
                              Archive
                            </Button>
                          }
                          title="Archive Project"
                          description={`Archive "${p.name}"? The simulation will be paused.`}
                          actionLabel="Archive"
                          variant="destructive"
                          onConfirm={() => handleArchive(p.id)}
                        />
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <NewProjectDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSubmit={handleCreate}
      />
    </AppLayout>
  );
}
