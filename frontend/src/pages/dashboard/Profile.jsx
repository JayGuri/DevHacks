import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import {
  Pencil,
  Lock,
  ChevronUp,
  ChevronDown,
  Shield,
  Zap,
  KeyRound,
  FolderOpen,
  Hash,
  Activity,
  Clock,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from "recharts";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import { MOCK_PROJECTS } from "@/lib/mockData";
import { getInitials, formatPercent, clampVal, randomBetween } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import StatCard from "@/components/dashboard/StatCard";
import RoleBadge from "@/components/dashboard/RoleBadge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const LINE_COLORS = ["#06b6d4", "#f59e0b", "#10b981", "#8b5cf6"];

function SortableHead({ label, sortKey, current, dir, onSort }) {
  const active = current === sortKey;
  return (
    <TableHead>
      <button
        className="flex items-center gap-1"
        onClick={() => onSort(sortKey)}
      >
        {label}
        {active &&
          (dir === "asc" ? (
            <ChevronUp size={12} />
          ) : (
            <ChevronDown size={12} />
          ))}
      </button>
    </TableHead>
  );
}

export default function Profile() {
  const { currentUser } = useAuth();
  const viewMode = useStore((s) => s.viewMode);
  const store = useStore();
  const navigate = useNavigate();

  const joinedIds = store.userProjects[currentUser?.id] || [];
  const joinedProjects = MOCK_PROJECTS.filter((p) =>
    joinedIds.includes(p.id)
  );

  // Inline name editing
  const [editing, setEditing] = useState(false);
  const [nameVal, setNameVal] = useState(currentUser?.name || "");

  // Sort state
  const [sortKey, setSortKey] = useState("project");
  const [sortDir, setSortDir] = useState("asc");

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  // Build per-project rows
  const rows = useMemo(() => {
    return joinedProjects.map((p) => {
      const member = p.members.find((m) => m.userId === currentUser?.id);
      const nodes = store.nodesByProject[p.id] || [];
      const myNode = nodes.find((n) => n.displayId === member?.nodeId);
      const numRounds = p.config.numRounds || 50;
      const rc = myNode?.roundsContributed || 0;
      return {
        projectId: p.id,
        project: p.name,
        nodeId: member?.nodeId || "—",
        rounds: rc,
        trust: myNode?.trust ?? 0,
        uptime: myNode ? Math.min(100, (rc / numRounds) * 100) : 0,
        status: myNode?.status || "—",
      };
    });
  }, [joinedProjects, currentUser, store.nodesByProject]);

  const sorted = useMemo(() => {
    return [...rows].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp = typeof av === "string" ? av.localeCompare(bv) : av - bv;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [rows, sortKey, sortDir]);

  // Achievements
  const hasHighTrust = rows.some((r) => r.trust > 0.85);
  const totalRoundsAll = rows.reduce((s, r) => s + r.rounds, 0);
  const hasPowerUser = totalRoundsAll > 50;
  const hasPrivacyChampion = joinedProjects.some(
    (p) => p.config.useDifferentialPrivacy
  );

  // Trust history for detailed chart
  const trustChartData = useMemo(() => {
    const maxLen = 30;
    return Array.from({ length: maxLen }, (_, i) => {
      const point = { round: i + 1 };
      joinedProjects.forEach((p, pi) => {
        const member = p.members.find((m) => m.userId === currentUser?.id);
        const nodes = store.nodesByProject[p.id] || [];
        const myNode = nodes.find((n) => n.displayId === member?.nodeId);
        point[p.id] = clampVal(
          (myNode?.trust || 0.8) + randomBetween(-0.06, 0.06),
          0.3,
          1.0
        );
      });
      return point;
    });
  }, [joinedProjects, currentUser, store.nodesByProject]);

  const totalUpdates = rows.reduce(
    (s, r) => s + r.rounds * 3,
    0
  );

  const userActivity = store.activityLog
    .filter((a) => a.userId === currentUser?.id)
    .slice(0, 20);

  return (
    <AppLayout title="Profile">
      {/* Section A — Header */}
      <Card className="mb-6">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
          <Avatar className="h-16 w-16">
            <AvatarFallback className="text-xl">
              {getInitials(currentUser?.name)}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              {editing ? (
                <div className="flex items-center gap-2">
                  <Input
                    value={nameVal}
                    onChange={(e) => setNameVal(e.target.value)}
                    className="h-8 w-48"
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
              ) : (
                <>
                  <h2 className="font-display text-2xl font-bold">
                    {nameVal}
                  </h2>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    onClick={() => setEditing(true)}
                  >
                    <Pencil size={14} />
                  </Button>
                </>
              )}
            </div>
            <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
              <Lock size={12} />
              {currentUser?.email}
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <RoleBadge role={currentUser?.role} />
              <span className="text-xs text-muted-foreground">
                Member since {currentUser?.createdAt}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {hasHighTrust && (
                <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  🛡 High Trust
                </Badge>
              )}
              {hasPowerUser && (
                <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400">
                  ⚡ Power User
                </Badge>
              )}
              {hasPrivacyChampion && (
                <Badge className="bg-primary/10 text-primary">
                  🔒 Privacy Champion
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section B — Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Projects"
          value={joinedProjects.length}
          icon={FolderOpen}
        />
        <StatCard label="Rounds" value={totalRoundsAll} icon={Hash} />
        <StatCard
          label="Gradient Updates"
          value={totalUpdates}
          icon={Activity}
        />
        <StatCard
          label="Uptime"
          value={
            rows.length > 0
              ? formatPercent(
                  rows.reduce((s, r) => s + r.uptime, 0) / rows.length
                )
              : "0%"
          }
          icon={Clock}
        />
      </div>

      {/* Section C — Per-project table */}
      <h3 className="mb-3 font-display text-lg font-semibold">
        Project Contributions
      </h3>
      <div className="mb-6 overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHead
                label="Project"
                sortKey="project"
                current={sortKey}
                dir={sortDir}
                onSort={handleSort}
              />
              <TableHead>Node</TableHead>
              <SortableHead
                label="Rounds"
                sortKey="rounds"
                current={sortKey}
                dir={sortDir}
                onSort={handleSort}
              />
              <SortableHead
                label="Avg Trust"
                sortKey="trust"
                current={sortKey}
                dir={sortDir}
                onSort={handleSort}
              />
              <SortableHead
                label="Uptime%"
                sortKey="uptime"
                current={sortKey}
                dir={sortDir}
                onSort={handleSort}
              />
              <TableHead>Status</TableHead>
              <TableHead>View</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((r) => (
              <TableRow key={r.projectId}>
                <TableCell className="font-medium">{r.project}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="mono-data">
                    {r.nodeId}
                  </Badge>
                </TableCell>
                <TableCell className="mono-data">{r.rounds}</TableCell>
                <TableCell className="mono-data">
                  {formatPercent(r.trust * 100)}
                </TableCell>
                <TableCell className="mono-data">
                  {formatPercent(r.uptime)}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{r.status}</Badge>
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      navigate(`/dashboard/projects/${r.projectId}`)
                    }
                  >
                    View
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Section D — Trust history chart (detailed) */}
      {viewMode === "detailed" && joinedProjects.length > 0 && (
        <Card className="mb-6">
          <CardContent className="p-4">
            <p className="metric-label mb-2 text-muted-foreground">
              Trust History
            </p>
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trustChartData}>
                  <XAxis
                    dataKey="round"
                    tick={{
                      fontSize: 10,
                      fill: "hsl(var(--muted-foreground))",
                    }}
                  />
                  <YAxis
                    domain={[0, 1]}
                    tick={{
                      fontSize: 10,
                      fill: "hsl(var(--muted-foreground))",
                    }}
                  />
                  <Tooltip />
                  <Legend />
                  {joinedProjects.map((p, i) => (
                    <Line
                      key={p.id}
                      dataKey={p.id}
                      stroke={LINE_COLORS[i % LINE_COLORS.length]}
                      strokeWidth={1.5}
                      dot={false}
                      name={p.name}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Section E — Activity timeline (detailed) */}
      {viewMode === "detailed" && userActivity.length > 0 && (
        <div className="mb-6">
          <h3 className="mb-3 font-display text-lg font-semibold">
            Activity Timeline
          </h3>
          <div className="space-y-2">
            {userActivity.map((a, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
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
        </div>
      )}

      {/* Bottom callout */}
      <Card className="bg-muted">
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">
            You contributed{" "}
            <span className="font-medium text-foreground">
              {totalUpdates.toLocaleString()}
            </span>{" "}
            gradient updates across {joinedProjects.length} projects, shielding
            60,000+ training samples from direct exposure.
          </p>
        </CardContent>
      </Card>
    </AppLayout>
  );
}
