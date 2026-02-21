import { useState, useMemo } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, Mail, Trash2, Copy, RefreshCw,
  Globe, LockKeyhole, Crown, Server,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import useFL from "@/hooks/useFL";
import { MOCK_PROJECTS, MOCK_USERS } from "@/lib/mockData";
import { formatPercent, cn, generateInviteCode } from "@/lib/utils";
import { isProjectLead, getUserProjectRole, getPendingRequests, getAllProjects } from "@/lib/projectUtils";
import AppLayout from "@/components/layout/AppLayout";
import EmptyState from "@/components/dashboard/EmptyState";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import ControlPanel from "@/components/admin/ControlPanel";
import NodeMatrix from "@/components/fl/NodeMatrix";
import ConvergenceChart from "@/components/fl/ConvergenceChart";
import SABDPanel from "@/components/fl/SABDPanel";
import GanttTimeline from "@/components/fl/GanttTimeline";
import PrivacyGauge from "@/components/fl/PrivacyGauge";
import PageSkeleton from "@/components/dashboard/PageSkeleton";
import { fadeIn } from "@/lib/animations";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const SESSION_KEY = (id) => `tab-${id}-admin-detail`;
const VALID_TABS = ["server", "nodes", "members", "config"];

export default function AdminProjectDetail() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentUser } = useAuth();
  const store = useStore();
  const fl = useFL(id);
  const viewMode = store.viewMode;
  const nodesByProject = store.nodesByProject;

  const amLead = isProjectLead(currentUser?.id, id, store);

  const [members, setMembers] = useState(fl.project?.members || []);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [transferTarget, setTransferTarget] = useState(null);

  const urlTab = searchParams.get("tab");
  const savedTab = sessionStorage.getItem(SESSION_KEY(id));
  const defaultTab =
    (urlTab && VALID_TABS.includes(urlTab) ? urlTab : null) ||
    (savedTab && VALID_TABS.includes(savedTab) ? savedTab : "server");

  function handleTabChange(value) {
    sessionStorage.setItem(SESSION_KEY(id), value);
    setSearchParams({ tab: value }, { replace: true });
  }

  if (fl.loading) {
    return (
      <AppLayout pageHeader={{ title: "Loading...", icon: <Server size={18} /> }}>
        <PageSkeleton layout="project" />
      </AppLayout>
    );
  }

  if (!fl.project) {
    return (
      <AppLayout>
        <EmptyState message="Project not found." />
        <Link to="/admin/projects" className="mt-4 block text-center text-primary hover:underline">
          \u2190 Back to projects
        </Link>
      </AppLayout>
    );
  }

  const config = fl.project.config;
  const nodes = nodesByProject[id] || [];
  const allProjects = getAllProjects(store);
  const project = allProjects.find((p) => p.id === id) || fl.project;
  const isCreator = project.createdBy === currentUser?.id;

  const memberData = useMemo(
    () =>
      members.map((m) => {
        const node = nodes.find(
          (n) => n.displayId === m.nodeId || n.nodeId === m.nodeId
        );
        const projRole = getUserProjectRole(m.userId, id, store);
        const user = MOCK_USERS.find((u) => u.id === m.userId);
        return {
          ...m,
          globalRole: user?.role || "CONTRIBUTOR",
          projectRole: projRole || m.role,
          trust: node?.trust || 0,
          rounds: node?.roundsContributed || 0,
          status: node?.status || "UNKNOWN",
        };
      }),
    [members, nodes, id, store]
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

  function handleRoleChange(userId, userName, newRole) {
    store.setProjectRole(id, userId, newRole);
    store.pushActivity({
      type: "role_change",
      message: `${userName}'s project role changed to ${newRole}`,
      projectId: id,
      userId,
      timestamp: new Date().toISOString(),
    });
    store.pushNotification({
      type: "role_change",
      targetUserId: userId,
      message: `Your role in "${fl.project.name}" was changed to ${newRole}.`,
      projectId: id,
    });
    toast.success(`${userName} is now ${newRole} in this project`);
  }

  function handleTransferLead() {
    if (!transferTarget) return;
    store.setProjectRole(id, transferTarget, "lead");
    store.setProjectRole(id, currentUser.id, "contributor");
    const targetUser = members.find((m) => m.userId === transferTarget);
    store.pushActivity({
      type: "role_change",
      message: `Project lead transferred to ${targetUser?.userName || transferTarget}`,
      projectId: id,
      userId: currentUser.id,
      timestamp: new Date().toISOString(),
    });
    store.pushNotification({
      type: "role_change",
      targetUserId: transferTarget,
      message: `You are now the lead of "${fl.project.name}".`,
      projectId: id,
    });
    toast.success(`Lead transferred to ${targetUser?.userName}`);
    setTransferTarget(null);
  }

  function handleRegenerateCode() {
    const newCode = generateInviteCode();
    store.updateExtraProject(id, { inviteCode: newCode });
    toast.success(`New code: ${newCode}`);
  }

  function handleCopyCode(code) {
    navigator.clipboard.writeText(code);
    toast.success("Copied to clipboard");
  }

  const configFields = [
    { label: "Clients", value: config.numClients, desc: "Number of federated nodes" },
    { label: "Byzantine Fraction", value: config.byzantineFraction, desc: "Proportion of adversarial nodes" },
    { label: "Attack Type", value: config.attackType.replace(/_/g, " "), desc: "Simulated attack vector" },
    { label: "Aggregation", value: config.aggregationMethod.replace(/_/g, " "), desc: "Robust aggregation strategy" },
    { label: "Rounds", value: config.numRounds, desc: "Total training rounds" },
    { label: "Dirichlet \u03b1", value: config.dirichletAlpha, desc: "Non-IID data distribution parameter" },
    { label: "Differential Privacy", value: config.useDifferentialPrivacy ? "Enabled" : "Disabled", desc: "DP noise injection for gradient updates" },
    { label: "Noise Multiplier", value: config.dpNoiseMultiplier, desc: "\u03c3 for DP Gaussian noise" },
    { label: "Clip Norm", value: config.dpMaxGradNorm, desc: "Max gradient L2 norm before clipping" },
    { label: "SABD Alpha", value: config.sabdAlpha, desc: "Sensitivity-Aware Byzantine Detection threshold" },
    { label: "Local Epochs", value: config.localEpochs, desc: "Training epochs per round per client" },
  ];

  const currentInviteCode = project.inviteCode;
  const isPrivate = project.visibility === "private";

  const visibilityBadge = isPrivate ? (
    <Badge variant="outline" className="text-xs text-muted-foreground">
      <LockKeyhole size={10} className="mr-1" />Private
    </Badge>
  ) : (
    <Badge className="bg-emerald-500/10 text-xs text-emerald-600 dark:text-emerald-400">
      <Globe size={10} className="mr-1" />Public
    </Badge>
  );

  const subtitleParts = [
    config.numClients && `${config.numClients} clients`,
    config.aggregationMethod && config.aggregationMethod.replace(/_/g, " "),
    config.attackType && config.attackType.replace(/_/g, " "),
  ].filter(Boolean);

  return (
    <AppLayout
      pageHeader={{
        title: fl.project.name,
        subtitle: subtitleParts.join(" \u00b7 "),
        icon: <Server size={18} />,
        badge: visibilityBadge,
      }}
    >
      <Tabs value={defaultTab} onValueChange={handleTabChange}>
        <TabsList className="mb-4">
          <TabsTrigger value="server">Server View</TabsTrigger>
          <TabsTrigger value="nodes">Nodes</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger value="config">Configuration</TabsTrigger>
        </TabsList>

        <AnimatePresence mode="wait">
          <motion.div
            key={defaultTab + viewMode}
            variants={fadeIn}
            initial="hidden"
            animate="visible"
            exit="hidden"
          >
            {/* Server View */}
            {defaultTab === "server" && (
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
                  {amLead && <ControlPanel fl={fl} projectId={id} />}
                </div>
              </div>
            )}

            {/* Nodes */}
            {defaultTab === "nodes" && (
              <div className="space-y-4">
                {amLead && (
                  <div className="flex flex-wrap items-center gap-3">
                    <ConfirmDialog
                      trigger={
                        <Button variant="outline" className="text-destructive border-destructive/30">Block All Byzantine</Button>
                      }
                      title="Block All Byzantine Nodes"
                      description="This will block every unblocked byzantine node in this project."
                      actionLabel="Block All"
                      variant="destructive"
                      onConfirm={() => {
                        fl.nodes.filter((n) => n.isByzantine && !n.isBlocked).forEach((n) => fl.blockNode(n.nodeId));
                        toast.success("All byzantine nodes blocked");
                      }}
                    />
                  </div>
                )}
                <NodeMatrix
                  nodes={fl.nodes}
                  viewMode="detailed"
                  isAdmin={amLead}
                  onBlock={fl.blockNode}
                  onUnblock={fl.unblockNode}
                />
              </div>
            )}

            {/* Members */}
            {defaultTab === "members" && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  {amLead && (
                    <Button onClick={() => setInviteOpen(true)}>
                      <Mail size={14} className="mr-1" /> Invite
                    </Button>
                  )}
                  {isCreator && amLead && members.length > 1 && (
                    <Dialog open={!!transferTarget} onOpenChange={(o) => !o && setTransferTarget(null)}>
                      <Button variant="outline" onClick={() => setTransferTarget("")}>
                        <Crown size={14} className="mr-1" /> Transfer Lead
                      </Button>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Transfer Project Lead</DialogTitle>
                          <DialogDescription>
                            You will lose admin controls for this project. This cannot be undone easily.
                          </DialogDescription>
                        </DialogHeader>
                        <Select value={transferTarget || ""} onValueChange={setTransferTarget}>
                          <SelectTrigger><SelectValue placeholder="Select a member" /></SelectTrigger>
                          <SelectContent>
                            {members.filter((m) => m.userId !== currentUser?.id).map((m) => (
                              <SelectItem key={m.userId} value={m.userId}>{m.userName}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <DialogFooter>
                          <Button variant="outline" onClick={() => setTransferTarget(null)}>Cancel</Button>
                          <ConfirmDialog
                            trigger={<Button variant="destructive" disabled={!transferTarget}>Confirm Transfer</Button>}
                            title="Are you sure?"
                            description="You will be demoted to contributor and lose all admin controls for this project."
                            confirmLabel="Transfer"
                            destructive
                            onConfirm={handleTransferLead}
                          />
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  )}
                </div>

                <div className="overflow-x-auto rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Global Role</TableHead>
                        <TableHead>Project Role</TableHead>
                        <TableHead>Node</TableHead>
                        <TableHead>Joined</TableHead>
                        <TableHead>Rounds</TableHead>
                        <TableHead>Avg Trust</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {memberData.map((m) => (
                        <TableRow key={m.userId}>
                          <TableCell className="font-medium">{m.userName}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs">{m.globalRole === "TEAM_LEAD" ? "Team Lead" : "Contributor"}</Badge>
                          </TableCell>
                          <TableCell>
                            {amLead && m.userId !== currentUser?.id ? (
                              <Select
                                value={m.projectRole}
                                onValueChange={(v) => handleRoleChange(m.userId, m.userName, v)}
                              >
                                <SelectTrigger className="h-8 w-32">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="lead">Lead</SelectItem>
                                  <SelectItem value="contributor">Contributor</SelectItem>
                                </SelectContent>
                              </Select>
                            ) : (
                              <Badge variant="outline" className={cn(
                                m.projectRole === "lead"
                                  ? "border-cyan-500 text-cyan-600 dark:text-cyan-400"
                                  : ""
                              )}>
                                {m.projectRole}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="mono-data">{m.nodeId}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{m.joinedAt}</TableCell>
                          <TableCell className="mono-data">{m.rounds}</TableCell>
                          <TableCell className="mono-data">{formatPercent(m.trust * 100)}</TableCell>
                          <TableCell>
                            {amLead && m.userId !== currentUser?.id && m.projectRole !== "lead" && (
                              <ConfirmDialog
                                trigger={
                                  <Button size="sm" variant="ghost" className="text-destructive"><Trash2 size={14} /></Button>
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

                <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
                  <DialogContent>
                    <DialogHeader><DialogTitle>Invite Member</DialogTitle></DialogHeader>
                    <Input placeholder="Email address" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancel</Button>
                      <Button onClick={handleInvite}>Send Invite</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            )}

            {/* Configuration */}
            {defaultTab === "config" && (
              <div className="space-y-4">
                {amLead && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                    <p className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
                      <AlertTriangle size={16} />
                      Changing config resets the simulation.
                    </p>
                  </div>
                )}

                {amLead && (
                  <Card>
                    <CardContent className="space-y-3 p-4">
                      <div className="flex items-center gap-2">
                        {isPrivate ? (
                          <Badge variant="outline" className="text-muted-foreground"><LockKeyhole size={10} className="mr-1" /> Private</Badge>
                        ) : (
                          <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"><Globe size={10} className="mr-1" /> Public</Badge>
                        )}
                      </div>
                      {isPrivate && currentInviteCode && (
                        <div className="flex items-center gap-3">
                          <span className="metric-label text-muted-foreground">Invite Code</span>
                          <span className="mono-data text-lg font-bold tracking-widest">{currentInviteCode}</span>
                          <Button size="sm" variant="outline" onClick={() => handleCopyCode(currentInviteCode)}>
                            <Copy size={12} className="mr-1" /> Copy
                          </Button>
                          <ConfirmDialog
                            trigger={
                              <Button size="sm" variant="ghost"><RefreshCw size={12} className="mr-1" /> Regenerate</Button>
                            }
                            title="Regenerate Invite Code"
                            description="The old code will stop working immediately."
                            confirmLabel="Regenerate"
                            destructive
                            onConfirm={handleRegenerateCode}
                          />
                        </div>
                      )}
                      <div className="flex gap-2">
                        {!isPrivate && (
                          <ConfirmDialog
                            trigger={<Button size="sm" variant="outline"><LockKeyhole size={12} className="mr-1" /> Convert to Private</Button>}
                            title="Make Project Private"
                            description="Only users with the invite code will be able to request joining."
                            confirmLabel="Make Private"
                            onConfirm={() => {
                              const code = generateInviteCode();
                              store.updateExtraProject(id, { visibility: "private", inviteCode: code });
                              toast.success(`Project is now private. Code: ${code}`);
                            }}
                          />
                        )}
                        {isPrivate && (
                          <ConfirmDialog
                            trigger={<Button size="sm" variant="outline"><Globe size={12} className="mr-1" /> Make Public</Button>}
                            title="Make Project Public"
                            description="Anyone will be able to browse and request to join this project."
                            confirmLabel="Make Public"
                            onConfirm={() => {
                              store.updateExtraProject(id, { visibility: "public", inviteCode: null });
                              toast.success("Project is now public");
                            }}
                          />
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {configFields.map((f) => (
                    <div key={f.label} className="rounded-lg border border-border p-3">
                      <p className="metric-label text-muted-foreground">{f.label}</p>
                      <p className="mono-data mt-1 text-lg">{String(f.value)}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{f.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </Tabs>
    </AppLayout>
  );
}
