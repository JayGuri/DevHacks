import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, Mail, Trash2 } from "lucide-react";
import { useStore } from "@/lib/store";
import useFL from "@/hooks/useFL";
import { MOCK_PROJECTS } from "@/lib/mockData";
import { formatPercent, cn } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import EmptyState from "@/components/dashboard/EmptyState";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import ControlPanel from "@/components/admin/ControlPanel";
import NodeMatrix from "@/components/fl/NodeMatrix";
import ConvergenceChart from "@/components/fl/ConvergenceChart";
import SABDPanel from "@/components/fl/SABDPanel";
import GanttTimeline from "@/components/fl/GanttTimeline";
import PrivacyGauge from "@/components/fl/PrivacyGauge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
} from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

export default function AdminProjectDetail() {
  const { id } = useParams();
  const fl = useFL(id);
  const viewMode = useStore((s) => s.viewMode);
  const nodesByProject = useStore((s) => s.nodesByProject);

  const [members, setMembers] = useState(fl.project?.members || []);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [sortKey, setSortKey] = useState("trust");

  if (!fl.project) {
    return (
      <AppLayout title="Project Detail">
        <EmptyState message="Project not found." />
        <Link to="/admin/projects" className="mt-4 block text-center text-primary hover:underline">
          ← Back to projects
        </Link>
      </AppLayout>
    );
  }

  const config = fl.project.config;
  const nodes = nodesByProject[id] || [];

  const memberData = useMemo(
    () =>
      members.map((m) => {
        const node = nodes.find(
          (n) => n.displayId === m.nodeId || n.nodeId === m.nodeId
        );
        return {
          ...m,
          trust: node?.trust || 0,
          rounds: node?.roundsContributed || 0,
          status: node?.status || "UNKNOWN",
        };
      }),
    [members, nodes]
  );

  function handleRemoveMember(userId) {
    setMembers((prev) => prev.filter((m) => m.userId !== userId));
    toast.success("Member removed");
  }

  function handleInvite() {
    if (!inviteEmail) return;
    toast.success(`Invitation sent to ${inviteEmail}`);
    setInviteEmail("");
    setInviteOpen(false);
  }

  const configFields = [
    { label: "Clients", value: config.numClients, desc: "Number of federated nodes" },
    { label: "Byzantine Fraction", value: config.byzantineFraction, desc: "Proportion of adversarial nodes" },
    { label: "Attack Type", value: config.attackType.replace(/_/g, " "), desc: "Simulated attack vector" },
    { label: "Aggregation", value: config.aggregationMethod.replace(/_/g, " "), desc: "Robust aggregation strategy" },
    { label: "Rounds", value: config.numRounds, desc: "Total training rounds" },
    { label: "Dirichlet α", value: config.dirichletAlpha, desc: "Non-IID data distribution parameter" },
    { label: "Differential Privacy", value: config.useDifferentialPrivacy ? "Enabled" : "Disabled", desc: "DP noise injection for gradient updates" },
    { label: "Noise Multiplier", value: config.dpNoiseMultiplier, desc: "σ for DP Gaussian noise" },
    { label: "Clip Norm", value: config.dpMaxGradNorm, desc: "Max gradient L2 norm before clipping" },
    { label: "SABD Alpha", value: config.sabdAlpha, desc: "Sensitivity-Aware Byzantine Detection threshold" },
    { label: "Local Epochs", value: config.localEpochs, desc: "Training epochs per round per client" },
  ];

  return (
    <AppLayout
      title={`${fl.project.name} — Admin`}
      breadcrumbs={[
        { label: "All Projects", href: "/admin/projects" },
        { label: fl.project.name },
      ]}
    >
      <Tabs defaultValue="server">
        <TabsList className="mb-4">
          <TabsTrigger value="server">Server View</TabsTrigger>
          <TabsTrigger value="nodes">Nodes</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger value="config">Configuration</TabsTrigger>
        </TabsList>

        {/* ── Server View ──────────────────────────── */}
        <TabsContent value="server">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle className="text-sm">Convergence</CardTitle></CardHeader>
              <CardContent className="h-64 min-h-[200px]">
                <ConvergenceChart rounds={fl.allRounds} viewMode={viewMode} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-sm">Timeline</CardTitle></CardHeader>
              <CardContent className="h-48 min-h-[200px]">
                <GanttTimeline ganttBlocks={fl.ganttBlocks} aggTriggerTimes={fl.aggTriggerTimes} nodes={fl.nodes} viewMode={viewMode} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-sm">SABD</CardTitle></CardHeader>
              <CardContent>
                <SABDPanel latestRound={fl.latestRound} allRounds={fl.allRounds} sabdAlpha={config.sabdAlpha} viewMode={viewMode} nodes={fl.nodes} />
              </CardContent>
            </Card>
            <div className="space-y-4">
              <Card>
                <CardContent className="p-4">
                  <PrivacyGauge latestRound={fl.latestRound} viewMode={viewMode} />
                </CardContent>
              </Card>
              <ControlPanel fl={fl} projectId={id} />
            </div>
          </div>
        </TabsContent>

        {/* ── Nodes ────────────────────────────────── */}
        <TabsContent value="nodes">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <ConfirmDialog
              trigger={
                <Button variant="outline" className="text-destructive border-destructive/30">
                  Block All Byzantine
                </Button>
              }
              title="Block All Byzantine Nodes"
              description="This will block every unblocked byzantine node in this project."
              actionLabel="Block All"
              variant="destructive"
              onConfirm={() => {
                fl.nodes
                  .filter((n) => n.isByzantine && !n.isBlocked)
                  .forEach((n) => fl.blockNode(n.nodeId));
                toast.success("All byzantine nodes blocked");
              }}
            />
          </div>
          <NodeMatrix
            nodes={fl.nodes}
            viewMode="detailed"
            isAdmin
            onBlock={fl.blockNode}
            onUnblock={fl.unblockNode}
          />
        </TabsContent>

        {/* ── Members ──────────────────────────────── */}
        <TabsContent value="members">
          <div className="mb-4 flex justify-end">
            <Button onClick={() => setInviteOpen(true)}>
              <Mail size={14} className="mr-1" /> Invite
            </Button>
          </div>

          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Node</TableHead>
                  <TableHead>Joined</TableHead>
                  <TableHead>Rounds</TableHead>
                  <TableHead>Avg Trust</TableHead>
                  <TableHead>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {memberData.map((m) => (
                  <TableRow key={m.userId}>
                    <TableCell className="font-medium">{m.userName}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{m.role}</Badge>
                    </TableCell>
                    <TableCell className="mono-data">{m.nodeId}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{m.joinedAt}</TableCell>
                    <TableCell className="mono-data">{m.rounds}</TableCell>
                    <TableCell className="mono-data">{formatPercent(m.trust * 100)}</TableCell>
                    <TableCell>
                      {m.role !== "lead" && (
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="ghost" className="text-destructive">
                              <Trash2 size={14} />
                            </Button>
                          }
                          title="Remove Member"
                          description={`Remove ${m.userName} from this project?`}
                          actionLabel="Remove"
                          variant="destructive"
                          onConfirm={() => handleRemoveMember(m.userId)}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Invite dialog */}
          <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Invite Member</DialogTitle>
              </DialogHeader>
              <Input placeholder="Email address" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
              <DialogFooter>
                <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancel</Button>
                <Button onClick={handleInvite}>Send Invite</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </TabsContent>

        {/* ── Configuration ────────────────────────── */}
        <TabsContent value="config">
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <p className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
              <AlertTriangle size={16} />
              Changing config resets the simulation.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {configFields.map((f) => (
              <div key={f.label} className="rounded-lg border border-border p-3">
                <p className="metric-label text-muted-foreground">{f.label}</p>
                <p className="mono-data mt-1 text-lg">{String(f.value)}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{f.desc}</p>
              </div>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </AppLayout>
  );
}
