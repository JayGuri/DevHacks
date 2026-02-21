import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Layers, Server, ShieldAlert, TrendingUp, Lock } from "lucide-react";
import { useStore } from "@/lib/store";
import { MOCK_PROJECTS } from "@/lib/mockData";
import { formatPercent, formatRound, getTrustColor } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import StatCard from "@/components/dashboard/StatCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const PROJECT_COLORS = ["#06b6d4", "#f59e0b", "#10b981"];

export default function AdminOverview() {
  const viewMode = useStore((s) => s.viewMode);
  const nodesByProject = useStore((s) => s.nodesByProject);
  const roundsByProject = useStore((s) => s.roundsByProject);

  const allNodes = useMemo(
    () => MOCK_PROJECTS.flatMap((p) => nodesByProject[p.id] || []),
    [nodesByProject]
  );

  const latestRounds = MOCK_PROJECTS.map((p) => {
    const r = roundsByProject[p.id] || [];
    return r[r.length - 1] || null;
  });

  const totalNodes = allNodes.length;
  const byzantineDetected = allNodes.filter(
    (n) => n.status === "BYZANTINE" || n.isByzantine
  ).length;
  const avgAccuracy =
    latestRounds.filter(Boolean).length > 0
      ? latestRounds.reduce((s, r) => s + (r?.globalAccuracy || 0), 0) /
        latestRounds.filter(Boolean).length
      : 0;
  const totalEpsilon = latestRounds.reduce(
    (s, r) => s + (r?.epsilonSpent || 0), 0
  );
  const avgFPR =
    latestRounds.filter(Boolean).length > 0
      ? latestRounds.reduce((s, r) => s + (r?.sabdFPR || 0), 0) /
        latestRounds.filter(Boolean).length
      : 0;
  const avgRecall =
    latestRounds.filter(Boolean).length > 0
      ? latestRounds.reduce((s, r) => s + (r?.sabdRecall || 0), 0) /
        latestRounds.filter(Boolean).length
      : 0;

  // Multi-project chart data
  const chartData = useMemo(() => {
    const maxLen = Math.max(
      ...MOCK_PROJECTS.map((p) => (roundsByProject[p.id] || []).length), 1
    );
    return Array.from({ length: maxLen }, (_, i) => {
      const point = { round: i + 1 };
      MOCK_PROJECTS.forEach((p) => {
        const r = (roundsByProject[p.id] || [])[i];
        point[p.id] = r?.globalAccuracy || 0;
      });
      return point;
    });
  }, [roundsByProject]);

  // Cluster health: all nodes with their project id
  const clusterNodes = useMemo(
    () =>
      MOCK_PROJECTS.flatMap((p) =>
        (nodesByProject[p.id] || []).map((n) => ({
          ...n,
          projectId: p.id,
          projectName: p.name,
        }))
      ),
    [nodesByProject]
  );

  const byzantineNodes = clusterNodes.filter(
    (n) => n.isByzantine || n.status === "BYZANTINE"
  );

  return (
    <AppLayout title="System Overview">
      {/* Stat cards */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Projects" value={MOCK_PROJECTS.length} icon={Layers} />
        <StatCard label="Total Nodes" value={totalNodes} icon={Server} />
        <StatCard
          label="Byzantine"
          value={byzantineDetected}
          icon={ShieldAlert}
          color={byzantineDetected > 0 ? "text-rose-500" : ""}
        />
        <StatCard
          label="Avg Accuracy"
          value={formatPercent(avgAccuracy)}
          icon={TrendingUp}
          color="text-emerald-500"
        />
        <StatCard
          label="Total ε"
          value={totalEpsilon.toFixed(2)}
          icon={Lock}
        />
      </div>

      {/* Detailed: extra stats row */}
      {viewMode === "detailed" && (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Active Projects" value={MOCK_PROJECTS.filter((p) => p.isActive).length} icon={Layers} color="text-emerald-500" />
          <StatCard label="Blocked Nodes" value={allNodes.filter((n) => n.isBlocked).length} icon={Server} color="text-muted-foreground" />
          <StatCard label="Avg FPR" value={formatPercent(avgFPR * 100)} color={avgFPR > 0.3 ? "text-rose-500" : "text-emerald-500"} />
          <StatCard label="Avg Recall" value={formatPercent(avgRecall * 100)} color="text-emerald-500" />
        </div>
      )}

      {/* Main 2-col grid */}
      <div className="mb-6 grid gap-4 lg:grid-cols-5">
        {/* Left: convergence chart */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-sm">Multi-Project Convergence</CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="round" tickFormatter={formatRound} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                <YAxis tickFormatter={(v) => v + "%"} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} domain={[0, 100]} />
                <Tooltip formatter={(v) => formatPercent(v)} />
                {MOCK_PROJECTS.map((p, i) => (
                  <Line key={p.id} dataKey={p.id} stroke={PROJECT_COLORS[i]} strokeWidth={2} dot={false} name={p.name} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Right: cluster health */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">Cluster Health</CardTitle>
          </CardHeader>
          <CardContent className="max-h-80 overflow-y-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Node</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Trust</TableHead>
                  {viewMode === "detailed" && <TableHead>Cos. Dist</TableHead>}
                  {viewMode === "detailed" && <TableHead>Staleness</TableHead>}
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clusterNodes.slice(0, 30).map((n) => (
                  <TableRow key={`${n.projectId}-${n.nodeId}`}>
                    <TableCell className="mono-data text-xs">{n.displayId}</TableCell>
                    <TableCell>
                      <Link to={`/admin/projects/${n.projectId}`} className="text-xs text-primary hover:underline">
                        {n.projectName.split(" ")[0]}
                      </Link>
                    </TableCell>
                    <TableCell className={`mono-data text-xs ${getTrustColor(n.trust)}`}>
                      {formatPercent(n.trust * 100)}
                    </TableCell>
                    {viewMode === "detailed" && (
                      <TableCell className={`mono-data text-xs ${n.cosineDistance > 0.45 ? "text-rose-500" : "text-muted-foreground"}`}>
                        {n.cosineDistance?.toFixed(3) || "—"}
                      </TableCell>
                    )}
                    {viewMode === "detailed" && (
                      <TableCell className="mono-data text-xs">{n.staleness ?? 0}R</TableCell>
                    )}
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]">{n.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* SABD summary */}
      <h3 className="mb-3 font-display text-lg font-semibold">SABD Performance</h3>
      <div className="mb-4 grid grid-cols-2 gap-4">
        <StatCard label="Avg FPR" value={formatPercent(avgFPR * 100)} color={avgFPR > 0.3 ? "text-rose-500" : "text-emerald-500"} />
        <StatCard label="Avg Recall" value={formatPercent(avgRecall * 100)} color="text-emerald-500" />
      </div>

      {byzantineNodes.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Node</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Trust</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {byzantineNodes.map((n) => (
                <TableRow key={`byz-${n.projectId}-${n.nodeId}`} className="bg-rose-500/5">
                  <TableCell className="mono-data">{n.displayId}</TableCell>
                  <TableCell>{n.projectName}</TableCell>
                  <TableCell><Badge variant="outline" className="border-rose-500 text-rose-500">{n.status}</Badge></TableCell>
                  <TableCell className="mono-data text-rose-500">{formatPercent(n.trust * 100)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </AppLayout>
  );
}
