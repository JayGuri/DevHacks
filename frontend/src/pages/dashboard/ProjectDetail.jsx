import { useState, useMemo } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import { Cpu, Globe, LockKeyhole } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import useFL from "@/hooks/useFL";
import useContributorStats from "@/hooks/useContributorStats";
import { formatPercent, getTrustColor, cn } from "@/lib/utils";
import { isProjectLead, getUserProjectRole, getPendingRequests, getAllProjects } from "@/lib/projectUtils";
import { MOCK_USERS } from "@/lib/mockData";
import AppLayout from "@/components/layout/AppLayout";
import StatCard from "@/components/dashboard/StatCard";
import EmptyState from "@/components/dashboard/EmptyState";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import NodeMatrix from "@/components/fl/NodeMatrix";
import ConvergenceChart from "@/components/fl/ConvergenceChart";
import GanttTimeline from "@/components/fl/GanttTimeline";
import PrivacyGauge from "@/components/fl/PrivacyGauge";
import SABDPanel from "@/components/fl/SABDPanel";
import ControlPanel from "@/components/admin/ControlPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Shield, Clock, Activity, Hash, Gauge, Layers,
  CheckCircle, XCircle,
} from "lucide-react";

const SESSION_KEY = (id) => `tab-${id}-project-detail`;
const VALID_TABS = ["mynode", "server", "admin"];

function getInitialTab(id, amLead) {
  // 1. Check URL param
  // (handled in parent via searchParams)
  // 2. Fall back to sessionStorage
  const saved = sessionStorage.getItem(SESSION_KEY(id));
  if (saved && VALID_TABS.includes(saved)) return saved;
  return "mynode";
}

export default function ProjectDetail() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentUser } = useAuth();
  const store = useStore();
  const viewMode = store.viewMode;
  const fl = useFL(id);
  const stats = useContributorStats(currentUser?.id, id);

  const amLead = isProjectLead(currentUser?.id, id, store);

  // Determine active tab: URL > sessionStorage > default
  const urlTab = searchParams.get("tab");
  const savedTab = sessionStorage.getItem(SESSION_KEY(id));
  const defaultTab =
    (urlTab && VALID_TABS.includes(urlTab) ? urlTab : null) ||
    (savedTab && VALID_TABS.includes(savedTab) ? savedTab : "mynode");

  function handleTabChange(value) {
    sessionStorage.setItem(SESSION_KEY(id), value);
    setSearchParams({ tab: value }, { replace: true });
  }

  if (!fl.project) {
    return (
      <AppLayout>
        <EmptyState message="Project not found." />
        <Link to="/dashboard/projects" className="mt-4 block text-center text-sm text-primary hover:underline">
          Back to projects
        </Link>
      </AppLayout>
    );
  }

  const isMember = fl.project.members.some((m) => m.userId === currentUser?.id);
  if (!isMember) {
    return (
      <AppLayout>
        <EmptyState message="You are not a member of this project." />
        <Link to="/dashboard/projects" className="mt-4 block text-center text-sm text-primary hover:underline">
          Browse projects
        </Link>
      </AppLayout>
    );
  }

  const trust = stats.myNode?.trust ?? 0;
  const avgTrust =
    fl.nodes.length > 0
      ? fl.nodes.reduce((s, n) => s + n.trust, 0) / fl.nodes.length
      : 0;

  const isPrivate = fl.project.visibility === "private";
  const visibilityBadge = isPrivate ? (
    <Badge variant="outline" className="text-xs text-muted-foreground">
      <LockKeyhole size={10} className="mr-1" />Private
    </Badge>
  ) : (
    <Badge className="bg-emerald-500/10 text-xs text-emerald-600 dark:text-emerald-400">
      <Globe size={10} className="mr-1" />Public
    </Badge>
  );

  const config = fl.project.config;
  const subtitleParts = [
    config.numClients && `${config.numClients} clients`,
    config.aggregationMethod && config.aggregationMethod.replace(/_/g, " "),
    config.attackType && config.attackType.replace(/_/g, " "),
  ].filter(Boolean);

  return (
    <AppLayout
      pageHeader={{
        title: fl.project.name,
        subtitle: subtitleParts.join(" · "),
        icon: <Cpu size={18} />,
        badge: visibilityBadge,
      }}
    >
      <Tabs value={defaultTab} onValueChange={handleTabChange}>
        <TabsList className="mb-4">
          <TabsTrigger value="mynode">My Node</TabsTrigger>
          <TabsTrigger value="server">Server Metrics</TabsTrigger>
          {amLead && <TabsTrigger value="admin">Project Admin</TabsTrigger>}
        </TabsList>

        {/* My Node */}
        <TabsContent value="mynode" className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Trust Score" value={formatPercent(trust * 100)} icon={Shield} color={getTrustColor(trust)} />
            <StatCard label="Status" value={stats.myNode?.status || "—"} icon={Activity} />
            <StatCard label="Staleness" value={`${stats.myNode?.staleness ?? 0}R`} icon={Clock} />
            <StatCard label="Rounds" value={stats.roundsContributed} icon={Hash} />
          </div>

          <Card>
            <CardContent className="space-y-3 p-4">
              <p className="metric-label text-muted-foreground">Your Trust vs Cluster Average</p>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="w-16 text-xs text-muted-foreground">You</span>
                  <Progress value={trust * 100} className="flex-1 h-2"
                    indicatorClassName={trust >= 0.7 ? "bg-emerald-500" : trust >= 0.4 ? "bg-amber-500" : "bg-rose-500"} />
                  <span className="mono-data w-14 text-right text-xs">{formatPercent(trust * 100)}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-16 text-xs text-muted-foreground">Avg</span>
                  <Progress value={avgTrust * 100} className="flex-1 h-2" />
                  <span className="mono-data w-14 text-right text-xs">{formatPercent(avgTrust * 100)}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {viewMode === "detailed" && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <StatCard label="Cos. Distance" value={(stats.myNode?.cosineDistance ?? 0).toFixed(3)} icon={Gauge} />
                <StatCard label="Gradient Updates" value={stats.totalUpdates} icon={Layers} />
              </div>
              <Card>
                <CardHeader><CardTitle className="text-sm">Privacy</CardTitle></CardHeader>
                <CardContent><PrivacyGauge latestRound={fl.latestRound} viewMode="detailed" /></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">Convergence (read-only)</CardTitle></CardHeader>
                <CardContent className="h-64 min-h-[200px]">
                  <ConvergenceChart rounds={fl.allRounds} viewMode={viewMode} />
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* Server Metrics (read-only) */}
        <TabsContent value="server" className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-sm">Model Convergence</CardTitle></CardHeader>
            <CardContent className="h-72 min-h-[200px]">
              <ConvergenceChart rounds={fl.allRounds} viewMode={viewMode} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">SABD Detection</CardTitle></CardHeader>
            <CardContent>
              <SABDPanel latestRound={fl.latestRound} allRounds={fl.allRounds} sabdAlpha={fl.project.config.sabdAlpha} viewMode={viewMode} nodes={fl.nodes} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">Training Timeline</CardTitle></CardHeader>
            <CardContent className="h-64 min-h-[200px]">
              <GanttTimeline ganttBlocks={fl.ganttBlocks} aggTriggerTimes={fl.aggTriggerTimes} nodes={fl.nodes} viewMode={viewMode} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">Privacy Budget</CardTitle></CardHeader>
            <CardContent><PrivacyGauge latestRound={fl.latestRound} viewMode={viewMode} /></CardContent>
          </Card>
        </TabsContent>

        {/* Project Admin (only visible to project leads) */}
        {amLead && (
          <TabsContent value="admin" className="space-y-6">
            <ProjectAdminTab
              fl={fl}
              projectId={id}
              currentUser={currentUser}
              store={store}
              viewMode={viewMode}
            />
          </TabsContent>
        )}
      </Tabs>
    </AppLayout>
  );
}

function ProjectAdminTab({ fl, projectId, currentUser, store, viewMode }) {
  const [members] = useState(fl.project?.members || []);
  const pendingRequests = getPendingRequests(projectId, store);
  const nodesByProject = store.nodesByProject;
  const nodes = nodesByProject[projectId] || [];

  const memberData = useMemo(
    () =>
      members.map((m) => {
        const node = nodes.find((n) => n.displayId === m.nodeId || n.nodeId === m.nodeId);
        const projRole = getUserProjectRole(m.userId, projectId, store);
        const user = MOCK_USERS.find((u) => u.id === m.userId);
        return {
          ...m,
          globalRole: user?.role || "CONTRIBUTOR",
          projectRole: projRole || m.role,
          trust: node?.trust || 0,
          rounds: node?.roundsContributed || 0,
        };
      }),
    [members, nodes, projectId, store]
  );

  function handleRoleChange(userId, userName, newRole) {
    store.setProjectRole(projectId, userId, newRole);
    store.pushNotification({
      type: "role_change",
      targetUserId: userId,
      message: `Your role in "${fl.project.name}" was changed to ${newRole}.`,
      projectId,
    });
    toast.success(`${userName} is now ${newRole} in this project`);
  }

  function handleApprove(req) {
    store.approveRequest(req.id, currentUser.id);
    store.pushNotification({
      type: "request_approved",
      targetUserId: req.userId,
      message: `Your request to join "${fl.project.name}" was approved.`,
      projectId,
    });
    toast.success(`${req.userName} approved`);
  }

  function handleReject(req) {
    store.rejectRequest(req.id, currentUser.id);
    store.pushNotification({
      type: "request_rejected",
      targetUserId: req.userId,
      message: `Your request to join "${fl.project.name}" was not approved.`,
      projectId,
    });
    toast.info("Request rejected");
  }

  return (
    <>
      {/* Node management */}
      <Card>
        <CardHeader><CardTitle className="text-sm">Node Management</CardTitle></CardHeader>
        <CardContent>
          <NodeMatrix
            nodes={fl.nodes}
            viewMode="detailed"
            isAdmin
            onBlock={fl.blockNode}
            onUnblock={fl.unblockNode}
          />
        </CardContent>
      </Card>

      {/* Control Panel */}
      <ControlPanel fl={fl} projectId={projectId} />

      {/* Join Requests */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            Join Requests
            {pendingRequests.length > 0 && (
              <Badge className="bg-rose-500 text-white">{pendingRequests.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pendingRequests.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">No pending requests</p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Message</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pendingRequests.map((req) => (
                    <TableRow key={req.id}>
                      <TableCell className="font-medium">{req.userName}</TableCell>
                      <TableCell className="mono-data text-xs">{req.userEmail}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(req.requestedAt), { addSuffix: true })}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">{req.message || "—"}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <ConfirmDialog
                            trigger={<Button size="sm" className="bg-emerald-600 text-white hover:bg-emerald-700"><CheckCircle size={14} className="mr-1" /> Approve</Button>}
                            title="Approve Request"
                            description={`Allow ${req.userName} to join?`}
                            confirmLabel="Approve"
                            onConfirm={() => handleApprove(req)}
                          />
                          <ConfirmDialog
                            trigger={<Button size="sm" variant="ghost" className="text-rose-500"><XCircle size={14} className="mr-1" /> Reject</Button>}
                            title="Reject Request"
                            description={`Reject ${req.userName}'s request?`}
                            confirmLabel="Reject"
                            destructive
                            onConfirm={() => handleReject(req)}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Member Management */}
      <Card>
        <CardHeader><CardTitle className="text-sm">Members</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Global Role</TableHead>
                  <TableHead>Project Role</TableHead>
                  <TableHead>Node</TableHead>
                  <TableHead>Rounds</TableHead>
                  <TableHead>Trust</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {memberData.map((m) => (
                  <TableRow key={m.userId}>
                    <TableCell className="font-medium">{m.userName}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {m.globalRole === "TEAM_LEAD" ? "Team Lead" : "Contributor"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {m.userId !== currentUser?.id ? (
                        <Select value={m.projectRole} onValueChange={(v) => handleRoleChange(m.userId, m.userName, v)}>
                          <SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="lead">Lead</SelectItem>
                            <SelectItem value="contributor">Contributor</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge variant="outline" className="border-cyan-500 text-cyan-600 dark:text-cyan-400">{m.projectRole}</Badge>
                      )}
                    </TableCell>
                    <TableCell className="mono-data">{m.nodeId}</TableCell>
                    <TableCell className="mono-data">{m.rounds}</TableCell>
                    <TableCell className="mono-data">{formatPercent(m.trust * 100)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
