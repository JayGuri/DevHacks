import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import { MOCK_PROJECTS } from "@/lib/mockData";
import { formatPercent, getTrustColor } from "@/lib/utils";
import AppLayout from "@/components/layout/AppLayout";
import EmptyState from "@/components/dashboard/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FolderOpen, Users } from "lucide-react";

export default function Projects() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const userProjects = useStore((s) => s.userProjects);
  const joinProject = useStore((s) => s.joinProject);
  const pushActivity = useStore((s) => s.pushActivity);
  const roundsByProject = useStore((s) => s.roundsByProject);
  const nodesByProject = useStore((s) => s.nodesByProject);

  const joinedIds = userProjects[currentUser?.id] || [];
  const joined = MOCK_PROJECTS.filter((p) => joinedIds.includes(p.id));
  const available = MOCK_PROJECTS.filter((p) => !joinedIds.includes(p.id));

  const [joinTarget, setJoinTarget] = useState(null);

  function handleJoin() {
    if (!joinTarget) return;
    joinProject(currentUser.id, joinTarget.id);
    pushActivity({
      type: "join",
      message: `Joined ${joinTarget.name}`,
      userId: currentUser.id,
      timestamp: new Date().toISOString(),
      projectId: joinTarget.id,
    });
    toast.success(`Joined ${joinTarget.name}`);
    setJoinTarget(null);
    navigate(`/dashboard/projects/${joinTarget.id}`);
  }

  function latestAccuracy(pid) {
    const rounds = roundsByProject[pid] || [];
    return rounds[rounds.length - 1]?.globalAccuracy || 0;
  }

  function myTrust(project) {
    const member = project.members.find(
      (m) => m.userId === currentUser?.id
    );
    const nodes = nodesByProject[project.id] || [];
    const node = nodes.find((n) => n.displayId === member?.nodeId);
    return node?.trust ?? 0;
  }

  function myNodeId(project) {
    const member = project.members.find(
      (m) => m.userId === currentUser?.id
    );
    return member?.nodeId || "—";
  }

  const nextSlot = (project) => {
    const letters = "ABCDEFGHIJ";
    const idx = project.members.length;
    const letter = letters[idx] || "X";
    return `NODE_${letter}${(idx % 3) + 1}`;
  };

  return (
    <AppLayout title="My Projects">
      <Tabs defaultValue="joined">
        <TabsList className="mb-4">
          <TabsTrigger value="joined">
            Joined ({joined.length})
          </TabsTrigger>
          <TabsTrigger value="available">
            Available ({available.length})
          </TabsTrigger>
        </TabsList>

        {/* Joined */}
        <TabsContent value="joined">
          {joined.length === 0 ? (
            <EmptyState
              icon={FolderOpen}
              message="You haven't joined any projects yet."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>My Node</TableHead>
                    <TableHead>Accuracy</TableHead>
                    <TableHead>My Trust</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {joined.map((p) => {
                    const trust = myTrust(p);
                    return (
                      <TableRow key={p.id}>
                        <TableCell className="font-medium">
                          {p.name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="mono-data">
                            {myNodeId(p)}
                          </Badge>
                        </TableCell>
                        <TableCell className="mono-data">
                          {formatPercent(latestAccuracy(p.id))}
                        </TableCell>
                        <TableCell
                          className={`mono-data ${getTrustColor(trust)}`}
                        >
                          {formatPercent(trust * 100)}
                        </TableCell>
                        <TableCell>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              navigate(`/dashboard/projects/${p.id}`)
                            }
                          >
                            View
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        {/* Available */}
        <TabsContent value="available">
          {available.length === 0 ? (
            <EmptyState
              icon={FolderOpen}
              message="You've joined all available projects."
            />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {available.map((p) => (
                <Card key={p.id}>
                  <CardContent className="space-y-3 p-4">
                    <p className="font-medium">{p.name}</p>
                    <p className="line-clamp-2 text-sm text-muted-foreground">
                      {p.description}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline">
                        <Users size={12} className="mr-1" />
                        {p.members.length} members
                      </Badge>
                      <Badge
                        variant="outline"
                        className="mono-data text-emerald-500"
                      >
                        {formatPercent(latestAccuracy(p.id))}
                      </Badge>
                      <Badge variant="outline" className="mono-data">
                        {p.config.attackType.replace("_", " ")}
                      </Badge>
                    </div>
                    <Button size="sm" onClick={() => setJoinTarget(p)}>
                      Join Project
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Join dialog */}
      <Dialog open={!!joinTarget} onOpenChange={() => setJoinTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Join {joinTarget?.name}</DialogTitle>
            <DialogDescription>
              You&apos;ll be assigned to this project as a contributor.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Assigned node</span>
              <Badge variant="outline" className="mono-data">
                {joinTarget && nextSlot(joinTarget)}
              </Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Clients</span>
              <span className="mono-data">
                {joinTarget?.config.numClients}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Attack</span>
              <span className="mono-data">
                {joinTarget?.config.attackType.replace("_", " ")}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Aggregator</span>
              <span className="mono-data">
                {joinTarget?.config.aggregationMethod.replace("_", " ")}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">
                Differential Privacy
              </span>
              <span className="mono-data">
                {joinTarget?.config.useDifferentialPrivacy ? "On" : "Off"}
              </span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setJoinTarget(null)}>
              Cancel
            </Button>
            <Button onClick={handleJoin}>Confirm &amp; Join</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
