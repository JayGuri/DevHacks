import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Search, Copy, Info } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import { USE_MOCK } from "@/lib/config";
import { apiListProjects, apiCreateProject, apiDeleteProject } from "@/lib/api";
import { formatPercent, cn, generateInviteCode } from "@/lib/utils";
import { getAllProjects } from "@/lib/projectUtils";
import AppLayout from "@/components/layout/AppLayout";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import NewProjectDialog from "@/components/admin/NewProjectDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

export default function AdminProjects() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const store = useStore();
  const viewMode = store.viewMode;
  const nodesByProject = store.nodesByProject;
  const roundsByProject = store.roundsByProject;

  const isGlobalLead = currentUser?.role === "TEAM_LEAD";

  // Fetch projects from API when not using mock
  useEffect(() => {
    if (!USE_MOCK) {
      apiListProjects()
        .then((data) => store.setProjects(data))
        .catch((err) => console.error("Failed to fetch projects:", err));
    }
  }, []);

  const allProjects = getAllProjects(store);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [successInfo, setSuccessInfo] = useState(null);

  const filtered = useMemo(
    () =>
      allProjects.filter(
        (p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) &&
          p.isActive !== false,
      ),
    [allProjects, search],
  );

  function latestAccuracy(pid) {
    const rounds = roundsByProject[pid] || [];
    return rounds[rounds.length - 1]?.globalAccuracy || 0;
  }

  function nodeCounts(pid) {
    const nodes = nodesByProject[pid] || [];
    const byz = nodes.filter(
      (n) => n.isByzantine || n.status === "BYZANTINE",
    ).length;
    return { byz, honest: nodes.length - byz };
  }

  async function handleCreate(data) {
    if (!USE_MOCK) {
      try {
        const created = await apiCreateProject(data);
        store.setProjects([...getAllProjects(store), created]);
        setDialogOpen(false);
        if (created.visibility === "private" && created.inviteCode) {
          setSuccessInfo({
            name: created.name,
            code: created.inviteCode,
            projectId: created.id,
          });
        } else {
          toast.success("Project created");
        }
      } catch (err) {
        toast.error(err.message || "Failed to create project");
      }
      return;
    }

    // Mock mode
    const id = `p${Date.now()}`;
    const isPrivate = data.visibility === "private";
    const inviteCode = isPrivate ? generateInviteCode() : null;
    const newProject = {
      id,
      name: data.name,
      description: data.description || "",
      createdBy: currentUser.id,
      createdAt: new Date().toISOString().split("T")[0],
      isActive: true,
      visibility: data.visibility || "public",
      inviteCode,
      joinRequests: [],
      maxMembers: 10,
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
          userId: currentUser.id,
          userName: currentUser.name,
          nodeId: "NODE_A1",
          role: "lead",
          joinedAt: new Date().toISOString().split("T")[0],
        },
      ],
    };
    store.addProject(newProject);
    store.setProjectRole(id, currentUser.id, "lead");
    store.joinProject(currentUser.id, id);
    setDialogOpen(false);

    if (isPrivate && inviteCode) {
      setSuccessInfo({ name: data.name, code: inviteCode, projectId: id });
    } else {
      toast.success("Project created");
    }
  }

  async function handleArchive(pid) {
    if (!USE_MOCK) {
      try {
        await apiDeleteProject(pid);
        store.setProjects(getAllProjects(store).filter((p) => p.id !== pid));
      } catch (err) {
        toast.error(err.message || "Failed to archive project");
        return;
      }
    } else {
      store.archiveProject(pid);
    }
    toast.success("Project archived");
  }

  function handleCopyCode() {
    if (successInfo?.code) {
      navigator.clipboard.writeText(successInfo.code);
      toast.success("Copied to clipboard");
    }
  }

  return (
    <AppLayout title="All Projects">
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
        {isGlobalLead ?
          <Button onClick={() => setDialogOpen(true)}>
            <Plus size={14} className="mr-1" /> New Project
          </Button>
        : <div className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
            <Info size={14} />
            Only Team Leads can create projects. Contact your organization's
            lead.
          </div>
        }
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Visibility</TableHead>
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
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {p.visibility === "private" ? "Private" : "Public"}
                    </Badge>
                  </TableCell>
                  <TableCell>{p.members.length}</TableCell>
                  <TableCell className="mono-data">
                    {formatPercent(latestAccuracy(p.id))}
                  </TableCell>
                  <TableCell className="mono-data">
                    <span className="text-rose-500">{byz}</span>/
                    <span className="text-emerald-500">{honest}</span>
                  </TableCell>
                  {viewMode === "detailed" && (
                    <TableCell className="text-xs">
                      {p.config?.attackType?.replace(/_/g, " ") || "—"}
                    </TableCell>
                  )}
                  {viewMode === "detailed" && (
                    <TableCell className="text-xs">
                      {p.config?.aggregationMethod?.replace(/_/g, " ") || "—"}
                    </TableCell>
                  )}
                  {viewMode === "detailed" && (
                    <TableCell className="mono-data text-xs">
                      {(
                        (roundsByProject[p.id] || []).slice(-1)[0]
                          ?.epsilonSpent || 0
                      ).toFixed(2)}
                    </TableCell>
                  )}
                  <TableCell className="text-xs text-muted-foreground">
                    {p.createdAt}
                  </TableCell>
                  <TableCell>
                    {p.isActive ?
                      <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                        Active
                      </Badge>
                    : <Badge
                        variant="outline"
                        className="text-muted-foreground"
                      >
                        Archived
                      </Badge>
                    }
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
                      {p.isActive && isGlobalLead && (
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

      {/* Success dialog for private projects with invite code */}
      <Dialog open={!!successInfo} onOpenChange={() => setSuccessInfo(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Project Created!</DialogTitle>
            <DialogDescription>
              Your private project "{successInfo?.name}" has been created.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Your invite code is:
            </p>
            <div className="flex items-center justify-center gap-3 rounded-lg border border-border bg-muted/50 p-4">
              <span className="mono-data text-2xl font-bold tracking-widest">
                {successInfo?.code}
              </span>
              <Button size="sm" variant="outline" onClick={handleCopyCode}>
                <Copy size={14} className="mr-1" /> Copy
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Share this code privately with contributors you want to invite.
            </p>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                setSuccessInfo(null);
                navigate(`/admin/projects/${successInfo?.projectId}`);
              }}
            >
              Go to Project
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
