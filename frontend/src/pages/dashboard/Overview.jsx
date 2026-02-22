import { useMemo, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  FolderOpen,
  Zap,
  Shield,
  Target,
  FolderPlus,
  ArrowRight,
  Layers,
  Lock,
  Radio,
  CheckCircle2,
  Pencil,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import { USE_MOCK } from "@/lib/config";
import { apiListProjects } from "@/lib/api";
import { getAllProjects } from "@/lib/projectUtils";
import { useFeatureGate } from "@/hooks/useFeatureGate";
import {
  getInitials,
  formatPercent,
  getTrustColor,
  getTrustBg,
} from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import StatCard from "@/components/dashboard/StatCard";
import RoleBadge from "@/components/dashboard/RoleBadge";
import EmptyState from "@/components/dashboard/EmptyState";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function ProjectCard({ project, userId, navigate, isTeamLead }) {
  const member = project.members.find((m) => m.userId === userId);
  const nodeId = member?.nodeId || "—";
  const rounds = useStore((s) => s.roundsByProject[project.id]) || [];
  const latest = rounds[rounds.length - 1];
  const accuracy = latest?.globalAccuracy || 0;
  const nodes = useStore((s) => s.nodesByProject[project.id]) || [];
  const myNode = nodes.find((n) => n.displayId === member?.nodeId);
  const trust = myNode?.trust ?? 0.87;

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        <p className="font-medium">{project.name}</p>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {project.description}
        </p>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="mono-data">
            {nodeId}
          </Badge>
          {/* Global model accuracy — Team Lead only */}
          {isTeamLead && (
            <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              {formatPercent(accuracy)}
            </Badge>
          )}
        </div>
        {isTeamLead && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Trust</span>
              <span className={getTrustColor(trust)}>
                {formatPercent(trust * 100)}
              </span>
            </div>
            <Progress value={trust * 100} className="h-1.5" />
          </div>
        )}
        {isTeamLead && (
          <Button
            variant="outline"
            size="sm"
            className="mt-auto"
            onClick={() => navigate(`/dashboard/projects/${project.id}`)}
          >
            View Project <ArrowRight size={14} className="ml-1" />
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export default function Overview() {
  const { currentUser } = useAuth();
  const { isTeamLead } = useFeatureGate();
  const store = useStore();
  const viewMode = store.viewMode;
  const userProjects = store.userProjects;
  const activityLog = store.activityLog;
  const roundsByProject = store.roundsByProject;
  const navigate = useNavigate();
  const setProjects = useStore((s) => s.setProjects);

  // Inline name editing
  const [editing, setEditing] = useState(false);
  const [nameVal, setNameVal] = useState(currentUser?.name || "");

  // Fetch projects from API when not using mock
  useEffect(() => {
    if (!USE_MOCK) {
      apiListProjects()
        .then((data) => setProjects(data))
        .catch((err) => console.error("Failed to fetch projects:", err));
    }
  }, [setProjects]);

  const allProjects = getAllProjects(store);

  const joinedProjects =
    USE_MOCK ?
      allProjects.filter((p) =>
        (userProjects[currentUser?.id] || []).includes(p.id),
      )
    : allProjects.filter((p) =>
        p.members?.some((m) => m.userId === currentUser?.id),
      );

  const totalRounds = joinedProjects.reduce((sum, p) => {
    const rounds = roundsByProject[p.id] || [];
    return sum + (rounds[rounds.length - 1]?.round || 0);
  }, 0);

  const bestAccuracy = joinedProjects.reduce((best, p) => {
    const rounds = roundsByProject[p.id] || [];
    const latest = rounds[rounds.length - 1];
    return Math.max(best, latest?.globalAccuracy || 0);
  }, 0);

  const nodesByProject = store.nodesByProject;

  const recentActivity = activityLog
    .filter((a) => a.userId === currentUser?.id)
    .slice(0, 5);

  // Compute real average trust across all user's nodes
  const avgTrust = useMemo(() => {
    let sum = 0,
      count = 0;
    joinedProjects.forEach((pid_or_p) => {
      const pId = typeof pid_or_p === "string" ? pid_or_p : pid_or_p.id;
      const project = allProjects.find((p) => p.id === pId) || pid_or_p;
      const member = project?.members?.find(
        (m) => m.userId === currentUser?.id,
      );
      const nodes = nodesByProject[pId] || [];
      const myNode = nodes.find((n) => n.displayId === member?.nodeId);
      if (myNode) {
        sum += myNode.trust;
        count++;
      }
    });
    return count > 0 ? sum / count : 0;
  }, [joinedProjects, nodesByProject, currentUser, allProjects]);

  // Detailed: per-project stats table
  const projectRows = useMemo(() => {
    return joinedProjects.map((p) => {
      const member = p.members.find((m) => m.userId === currentUser?.id);
      const nodes = nodesByProject[p.id] || [];
      const myNode = nodes.find((n) => n.displayId === member?.nodeId);
      const rounds = roundsByProject[p.id] || [];
      const latest = rounds[rounds.length - 1];
      return {
        id: p.id,
        name: p.name,
        nodeId: member?.nodeId || "—",
        trust: myNode?.trust ?? 0,
        accuracy: latest?.globalAccuracy || 0,
        rounds: myNode?.roundsContributed || 0,
        epsilon: latest?.epsilonSpent || 0,
        status: myNode?.status || "—",
      };
    });
  }, [joinedProjects, currentUser, nodesByProject, roundsByProject]);

  // First joined project's node for the Client node status panel
  const clientNode = useMemo(() => {
    if (isTeamLead || joinedProjects.length === 0) return null;
    const firstProject = joinedProjects[0];
    const member = firstProject.members?.find(
      (m) => m.userId === currentUser?.id,
    );
    const nodes = nodesByProject[firstProject.id] || [];
    return nodes.find((n) => n.displayId === member?.nodeId) || null;
  }, [isTeamLead, joinedProjects, currentUser, nodesByProject]);

  return (
    <AppLayout title="Overview">
      {/* Client-only: Node Status Banner */}
      {!isTeamLead && (
        <Card className="mb-6 border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="flex items-center gap-4 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10">
              <Radio size={20} className="animate-pulse text-emerald-500" />
            </div>
            <div className="flex-1">
              <p className="font-semibold text-emerald-600 dark:text-emerald-400">
                Your node is live and connected
              </p>
              <p className="text-sm text-muted-foreground">
                {clientNode ?
                  `Node ${clientNode.displayId} — local training round is being recorded`
                : "Join a project to activate your node"}
              </p>
            </div>
            {clientNode && (
              <CheckCircle2 size={20} className="text-emerald-500" />
            )}
          </CardContent>
        </Card>
      )}

      {/* Profile hero — with inline name edit */}
      <Card className="mb-6">
        <CardContent className="flex items-center gap-4 p-5">
          <Avatar className="h-14 w-14">
            <AvatarFallback className="text-lg">
              {getInitials(nameVal || currentUser?.name)}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            {editing ?
              <div className="flex items-center gap-2">
                <Input
                  value={nameVal}
                  onChange={(e) => setNameVal(e.target.value)}
                  className="h-8 w-48"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setEditing(false);
                    if (e.key === "Escape") {
                      setNameVal(currentUser?.name || "");
                      setEditing(false);
                    }
                  }}
                />
                <Button size="sm" onClick={() => setEditing(false)}>
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setNameVal(currentUser?.name || "");
                    setEditing(false);
                  }}
                >
                  Cancel
                </Button>
              </div>
            : <div className="flex items-center gap-2">
                <h2 className="font-display text-2xl font-bold truncate">
                  {nameVal || currentUser?.name}
                </h2>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7 shrink-0"
                  onClick={() => setEditing(true)}
                  title="Edit display name"
                >
                  <Pencil size={13} />
                </Button>
              </div>
            }
            <div className="mt-1 flex items-center gap-2">
              <RoleBadge role={currentUser?.role} />
              <span className="text-xs text-muted-foreground">
                Member since {currentUser?.createdAt}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stat cards */}
      {isTeamLead && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Total Projects"
            value={joinedProjects.length}
            icon={FolderOpen}
          />
          <StatCard label="Total Rounds" value={totalRounds} icon={Zap} />
          <StatCard
            label="Avg Trust"
            value={formatPercent(avgTrust * 100)}
            icon={Shield}
            color="text-emerald-500"
          />
          {/* Global model accuracy — Team Lead only */}
          <StatCard
            label="Best Accuracy"
            value={formatPercent(bestAccuracy)}
            icon={Target}
            color="text-primary"
          />
        </div>
      )}

      {/* Extra stat cards (team lead only) */}
      {isTeamLead && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Avg Epsilon"
            value={
              projectRows.length > 0 ?
                (
                  projectRows.reduce((s, r) => s + r.epsilon, 0) /
                  projectRows.length
                ).toFixed(2)
              : "0"
            }
            icon={Lock}
          />
          <StatCard
            label="Total Gradient Updates"
            value={projectRows.reduce((s, r) => s + r.rounds * 3, 0)}
            icon={Layers}
          />
        </div>
      )}

      {/* My Projects — always detailed table */}
      <h3 className="mb-3 font-display text-lg font-semibold">My Projects</h3>
      {joinedProjects.length === 0 ?
        <EmptyState
          icon={FolderPlus}
          message="No projects yet. Join a project to start contributing."
        />
      : <div className="mb-6 overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Project</TableHead>
                <TableHead>Node</TableHead>
                {isTeamLead && <TableHead>Trust</TableHead>}
                {/* Model accuracy and privacy budget are global metrics — Team Lead only */}
                {isTeamLead && <TableHead>Accuracy</TableHead>}
                <TableHead>Rounds</TableHead>
                {isTeamLead && <TableHead>ε Spent</TableHead>}
                {isTeamLead && <TableHead>Status</TableHead>}
                {isTeamLead && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {projectRows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="mono-data">
                      {r.nodeId}
                    </Badge>
                  </TableCell>
                  {isTeamLead && (
                    <TableCell
                      className={`mono-data ${getTrustColor(r.trust)}`}
                    >
                      {formatPercent(r.trust * 100)}
                    </TableCell>
                  )}
                  {isTeamLead && (
                    <TableCell className="mono-data">
                      {formatPercent(r.accuracy)}
                    </TableCell>
                  )}
                  <TableCell className="mono-data">{r.rounds}</TableCell>
                  {isTeamLead && (
                    <TableCell className="mono-data">
                      {r.epsilon.toFixed(2)}
                    </TableCell>
                  )}
                  {isTeamLead && (
                    <TableCell>
                      <Badge variant="outline">{r.status}</Badge>
                    </TableCell>
                  )}
                  {isTeamLead && (
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/dashboard/projects/${r.id}`)}
                      >
                        View <ArrowRight size={14} className="ml-1" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      }

      {/* Recent activity — team lead only */}
      {isTeamLead && (
        <div>
          <h3 className="mb-3 font-display text-lg font-semibold">
            Recent Activity
          </h3>
          {recentActivity.length > 0 ?
            <div className="space-y-2">
              {recentActivity.map((a, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06 }}
                  className="flex items-center gap-3 rounded-md border border-border p-3"
                >
                  <Zap size={14} className="text-primary" />
                  <span className="flex-1 text-sm">
                    {a.message || `${a.type} — ${a.displayId || a.projectId}`}
                  </span>
                  <span className="mono-data text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(a.timestamp), {
                      addSuffix: true,
                    })}
                  </span>
                </motion.div>
              ))}
            </div>
          : <p className="text-sm text-muted-foreground">
              No recent activity yet. Join or interact with a project to see
              events here.
            </p>
          }
        </div>
      )}
    </AppLayout>
  );
}
