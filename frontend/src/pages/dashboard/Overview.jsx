import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { FolderOpen, Zap, Shield, Target, FolderPlus, ArrowRight } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import { MOCK_PROJECTS } from "@/lib/mockData";
import { getInitials, formatPercent, getTrustColor } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import StatCard from "@/components/dashboard/StatCard";
import RoleBadge from "@/components/dashboard/RoleBadge";
import EmptyState from "@/components/dashboard/EmptyState";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

function ProjectCard({ project, userId, navigate }) {
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
          <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            {formatPercent(accuracy)}
          </Badge>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Trust</span>
            <span className={getTrustColor(trust)}>
              {formatPercent(trust * 100)}
            </span>
          </div>
          <Progress value={trust * 100} className="h-1.5" />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="mt-auto"
          onClick={() => navigate(`/dashboard/projects/${project.id}`)}
        >
          View Project <ArrowRight size={14} className="ml-1" />
        </Button>
      </CardContent>
    </Card>
  );
}

export default function Overview() {
  const { currentUser } = useAuth();
  const viewMode = useStore((s) => s.viewMode);
  const userProjects = useStore((s) => s.userProjects);
  const activityLog = useStore((s) => s.activityLog);
  const roundsByProject = useStore((s) => s.roundsByProject);
  const navigate = useNavigate();

  const joinedIds = userProjects[currentUser?.id] || [];
  const joinedProjects = MOCK_PROJECTS.filter((p) => joinedIds.includes(p.id));

  const totalRounds = joinedIds.reduce((sum, pid) => {
    const rounds = roundsByProject[pid] || [];
    return sum + (rounds[rounds.length - 1]?.round || 0);
  }, 0);

  const bestAccuracy = joinedIds.reduce((best, pid) => {
    const rounds = roundsByProject[pid] || [];
    const latest = rounds[rounds.length - 1];
    return Math.max(best, latest?.globalAccuracy || 0);
  }, 0);

  const recentActivity = activityLog
    .filter((a) => a.userId === currentUser?.id)
    .slice(0, 5);

  return (
    <AppLayout title="Overview">
      {/* Profile hero */}
      <Card className="mb-6">
        <CardContent className="flex items-center gap-4 p-5">
          <Avatar className="h-14 w-14">
            <AvatarFallback className="text-lg">
              {getInitials(currentUser?.name)}
            </AvatarFallback>
          </Avatar>
          <div>
            <h2 className="font-display text-2xl font-bold">
              {currentUser?.name}
            </h2>
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
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Total Projects"
          value={joinedProjects.length}
          icon={FolderOpen}
        />
        <StatCard label="Total Rounds" value={totalRounds} icon={Zap} />
        <StatCard
          label="Avg Trust"
          value="87%"
          icon={Shield}
          color="text-emerald-500"
        />
        <StatCard
          label="Best Accuracy"
          value={formatPercent(bestAccuracy)}
          icon={Target}
          color="text-primary"
        />
      </div>

      {/* My Projects */}
      <h3 className="mb-3 font-display text-lg font-semibold">My Projects</h3>
      {joinedProjects.length === 0 ? (
        <EmptyState
          icon={FolderPlus}
          message="No projects yet. Join a project to start contributing."
        />
      ) : (
        <div className="mb-6 grid gap-4 md:grid-cols-2">
          {joinedProjects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              userId={currentUser?.id}
              navigate={navigate}
            />
          ))}
        </div>
      )}

      {/* Detailed: recent activity */}
      {viewMode === "detailed" && recentActivity.length > 0 && (
        <div>
          <h3 className="mb-3 font-display text-lg font-semibold">
            Recent Activity
          </h3>
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
        </div>
      )}
    </AppLayout>
  );
}
