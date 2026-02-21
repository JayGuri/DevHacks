import { useParams, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import useFL from "@/hooks/useFL";
import useContributorStats from "@/hooks/useContributorStats";
import { formatPercent, getTrustColor } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import StatCard from "@/components/dashboard/StatCard";
import EmptyState from "@/components/dashboard/EmptyState";
import ConvergenceChart from "@/components/fl/ConvergenceChart";
import GanttTimeline from "@/components/fl/GanttTimeline";
import PrivacyGauge from "@/components/fl/PrivacyGauge";
import SABDPanel from "@/components/fl/SABDPanel";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Shield, Clock, Activity, Hash, Gauge, Layers } from "lucide-react";

export default function ProjectDetail() {
  const { id } = useParams();
  const { currentUser } = useAuth();
  const viewMode = useStore((s) => s.viewMode);
  const fl = useFL(id);
  const stats = useContributorStats(currentUser?.id, id);

  if (!fl.project) {
    return (
      <AppLayout title="Project">
        <EmptyState message="Project not found." />
        <Link
          to="/dashboard/projects"
          className="mt-4 block text-center text-sm text-primary hover:underline"
        >
          Back to projects
        </Link>
      </AppLayout>
    );
  }

  const isMember = fl.project.members.some(
    (m) => m.userId === currentUser?.id
  );
  if (!isMember) {
    return (
      <AppLayout title={fl.project.name}>
        <EmptyState message="You are not a member of this project." />
        <Link
          to="/dashboard/projects"
          className="mt-4 block text-center text-sm text-primary hover:underline"
        >
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

  return (
    <AppLayout
      title={fl.project.name}
      breadcrumbs={[
        { label: "Projects", href: "/dashboard/projects" },
        { label: fl.project.name },
      ]}
    >
      <Tabs defaultValue="mynode">
        <TabsList className="mb-4">
          <TabsTrigger value="mynode">My Node</TabsTrigger>
          <TabsTrigger value="server">Server Metrics</TabsTrigger>
        </TabsList>

        {/* My Node */}
        <TabsContent value="mynode" className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Trust Score"
              value={formatPercent(trust * 100)}
              icon={Shield}
              color={getTrustColor(trust)}
            />
            <StatCard
              label="Status"
              value={stats.myNode?.status || "—"}
              icon={Activity}
            />
            <StatCard
              label="Staleness"
              value={`${stats.myNode?.staleness ?? 0}R`}
              icon={Clock}
            />
            <StatCard
              label="Rounds"
              value={stats.roundsContributed}
              icon={Hash}
            />
          </div>

          {/* Your trust vs cluster average */}
          <Card>
            <CardContent className="space-y-3 p-4">
              <p className="metric-label text-muted-foreground">
                Your Trust vs Cluster Average
              </p>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="w-16 text-xs text-muted-foreground">
                    You
                  </span>
                  <Progress
                    value={trust * 100}
                    className="flex-1 h-2"
                    indicatorClassName={
                      trust >= 0.7
                        ? "bg-emerald-500"
                        : trust >= 0.4
                          ? "bg-amber-500"
                          : "bg-rose-500"
                    }
                  />
                  <span className="mono-data w-14 text-right text-xs">
                    {formatPercent(trust * 100)}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-16 text-xs text-muted-foreground">
                    Avg
                  </span>
                  <Progress value={avgTrust * 100} className="flex-1 h-2" />
                  <span className="mono-data w-14 text-right text-xs">
                    {formatPercent(avgTrust * 100)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {viewMode === "detailed" && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <StatCard
                  label="Cos. Distance"
                  value={(stats.myNode?.cosineDistance ?? 0).toFixed(3)}
                  icon={Gauge}
                />
                <StatCard
                  label="Gradient Updates"
                  value={stats.totalUpdates}
                  icon={Layers}
                />
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Privacy</CardTitle>
                </CardHeader>
                <CardContent>
                  <PrivacyGauge
                    latestRound={fl.latestRound}
                    viewMode="detailed"
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">
                    Convergence (read-only)
                  </CardTitle>
                </CardHeader>
                <CardContent className="h-64 min-h-[200px]">
                  <ConvergenceChart
                    rounds={fl.allRounds}
                    viewMode={viewMode}
                  />
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {/* Server Metrics (read-only) */}
        <TabsContent value="server" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Model Convergence</CardTitle>
            </CardHeader>
            <CardContent className="h-72 min-h-[200px]">
              <ConvergenceChart rounds={fl.allRounds} viewMode={viewMode} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">SABD Detection</CardTitle>
            </CardHeader>
            <CardContent>
              <SABDPanel
                latestRound={fl.latestRound}
                allRounds={fl.allRounds}
                sabdAlpha={fl.project.config.sabdAlpha}
                viewMode={viewMode}
                nodes={fl.nodes}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Training Timeline</CardTitle>
            </CardHeader>
            <CardContent className="h-64 min-h-[200px]">
              <GanttTimeline
                ganttBlocks={fl.ganttBlocks}
                aggTriggerTimes={fl.aggTriggerTimes}
                nodes={fl.nodes}
                viewMode={viewMode}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Privacy Budget</CardTitle>
            </CardHeader>
            <CardContent>
              <PrivacyGauge
                latestRound={fl.latestRound}
                viewMode={viewMode}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </AppLayout>
  );
}
