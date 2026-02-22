import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";
import {
  FolderOpen,
  Users,
  KeyRound,
  Globe,
  LockKeyhole,
  ClipboardList,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useFeatureGate } from "@/hooks/useFeatureGate";
import { useStore } from "@/lib/store";
import { USE_MOCK } from "@/lib/config";
import {
  apiListProjects,
  apiCreateJoinRequest,
  apiValidateCode,
  apiListJoinRequests,
} from "@/lib/api";
import { formatPercent, getTrustColor, validateInviteCode } from "@/lib/utils";
import {
  getAllProjects,
  getAvailableToJoin,
  getUserPendingRequest,
} from "@/lib/projectUtils";
import AppLayout from "@/components/layout/AppLayout";
import EmptyState from "@/components/dashboard/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

export default function Projects() {
  const { currentUser } = useAuth();
  const { isTeamLead } = useFeatureGate();
  const navigate = useNavigate();
  const store = useStore();
  const userProjects = store.userProjects;
  const pushActivity = store.pushActivity;
  const roundsByProject = store.roundsByProject;
  const nodesByProject = store.nodesByProject;
  const submitJoinRequest = store.submitJoinRequest;
  const pushNotification = store.pushNotification;

  const joinedIds = userProjects[currentUser?.id] || [];
  const allProjects = getAllProjects(store);
  const joined =
    USE_MOCK ?
      allProjects.filter((p) => joinedIds.includes(p.id))
    : allProjects.filter((p) =>
        p.members?.some((m) => m.userId === currentUser?.id),
      );
  const available = getAvailableToJoin(currentUser?.id, store);

  const myRequests =
    USE_MOCK ?
      store.joinRequests.filter((r) => r.userId === currentUser?.id)
    : store.fetchedJoinRequests.filter((r) => r.userId === currentUser?.id);

  // Fetch data from API when not using mock
  useEffect(() => {
    if (!USE_MOCK) {
      apiListProjects()
        .then((data) => store.setProjects(data))
        .catch((err) => console.error("Failed to fetch projects:", err));
      apiListJoinRequests({ userId: currentUser?.id })
        .then((data) => store.setFetchedJoinRequests(data))
        .catch(() => {});
    }
  }, [currentUser?.id]);

  // Request-to-join dialog state
  const [requestTarget, setRequestTarget] = useState(null);
  const [requestMessage, setRequestMessage] = useState("");

  // Join-with-code dialog state
  const [codeDialogOpen, setCodeDialogOpen] = useState(false);
  const [inviteCode, setInviteCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [codeProject, setCodeProject] = useState(null);

  function latestAccuracy(pid) {
    const rounds = roundsByProject[pid] || [];
    return rounds[rounds.length - 1]?.globalAccuracy || 0;
  }

  function myTrust(project) {
    const member = project.members.find((m) => m.userId === currentUser?.id);
    const nodes = nodesByProject[project.id] || [];
    const node = nodes.find((n) => n.displayId === member?.nodeId);
    return node?.trust ?? 0;
  }

  function myNodeId(project) {
    const member = project.members.find((m) => m.userId === currentUser?.id);
    return member?.nodeId || "—";
  }

  function hasPendingRequest(projectId) {
    return !!getUserPendingRequest(currentUser?.id, projectId, store);
  }

  async function handleSubmitRequest(project) {
    if (!USE_MOCK) {
      try {
        const created = await apiCreateJoinRequest(project.id, requestMessage);
        store.setFetchedJoinRequests([...store.fetchedJoinRequests, created]);
        toast.info("Request sent — waiting for approval");
      } catch (err) {
        toast.error(err.message || "Failed to submit request");
      }
      setRequestTarget(null);
      setRequestMessage("");
      return;
    }

    // Mock mode
    const leadMember = project.members.find((m) => m.role === "lead");
    submitJoinRequest({
      userId: currentUser.id,
      userName: currentUser.name,
      userEmail: currentUser.email,
      projectId: project.id,
      message: requestMessage,
    });
    if (leadMember) {
      pushNotification({
        type: "join_request",
        title: "New Join Request",
        message: `${currentUser.name} requested to join ${project.name}`,
        projectId: project.id,
        fromUserId: currentUser.id,
        toUserId: leadMember.userId,
      });
    }
    pushActivity({
      type: "request",
      message: `Requested to join ${project.name}`,
      userId: currentUser.id,
      timestamp: new Date().toISOString(),
      projectId: project.id,
    });
    toast.info("Request sent — waiting for approval");
    setRequestTarget(null);
    setRequestMessage("");
  }

  async function handleCodeLookup() {
    setCodeError("");
    setCodeProject(null);

    if (!USE_MOCK) {
      try {
        const data = await apiValidateCode(inviteCode);
        if (!data.project) {
          setCodeError("Invalid or expired code");
          return;
        }
        setCodeProject(data.project);
      } catch (err) {
        setCodeError(err.message || "Invalid code");
      }
      return;
    }

    // Mock mode
    const found = validateInviteCode(inviteCode, allProjects);
    if (!found) {
      setCodeError("Invalid or expired code");
      return;
    }
    if (joinedIds.includes(found.id)) {
      setCodeError("You are already a member of this project.");
      return;
    }
    setCodeProject(found);
  }

  function handleCodeRequest() {
    if (!codeProject) return;
    handleSubmitRequest(codeProject);
    setCodeDialogOpen(false);
    setInviteCode("");
    setCodeProject(null);
  }

  function resetCodeDialog() {
    setCodeDialogOpen(false);
    setInviteCode("");
    setCodeError("");
    setCodeProject(null);
  }

  return (
    <AppLayout title="My Projects">
      <Tabs defaultValue="joined">
        <TabsList className="mb-4">
          <TabsTrigger value="joined">Joined ({joined.length})</TabsTrigger>
          <TabsTrigger value="available">
            Available ({available.length})
          </TabsTrigger>
          <TabsTrigger value="requests">
            My Requests ({myRequests.length})
          </TabsTrigger>
        </TabsList>

        {/* ── Joined ──────────────────────────── */}
        <TabsContent value="joined">
          {joined.length === 0 ?
            <EmptyState
              icon={FolderOpen}
              message="You haven't joined any projects yet."
            />
          : <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>My Node</TableHead>
                    {/* Global model accuracy — Team Lead only */}
                    {isTeamLead && <TableHead>Accuracy</TableHead>}
                    <TableHead>My Trust</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {joined.map((p) => {
                    const trust = myTrust(p);
                    return (
                      <TableRow key={p.id}>
                        <TableCell className="font-medium">{p.name}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="mono-data">
                            {myNodeId(p)}
                          </Badge>
                        </TableCell>
                        {isTeamLead && (
                          <TableCell className="mono-data">
                            {formatPercent(latestAccuracy(p.id))}
                          </TableCell>
                        )}
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
          }
        </TabsContent>

        {/* ── Available ───────────────────────── */}
        <TabsContent value="available">
          {/* Join with Code button */}
          <div className="mb-4">
            <Button variant="outline" onClick={() => setCodeDialogOpen(true)}>
              <KeyRound size={14} className="mr-1.5" /> Join with Code
            </Button>
          </div>

          {available.length === 0 ?
            <EmptyState
              icon={FolderOpen}
              message="No public projects available to join."
            />
          : <div className="grid gap-4 md:grid-cols-2">
              {available.map((p) => {
                const pending = hasPendingRequest(p.id);
                return (
                  <Card key={p.id}>
                    <CardContent className="space-y-3 p-4">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{p.name}</p>
                        <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                          <Globe size={10} className="mr-1" /> Public
                        </Badge>
                      </div>
                      <p className="line-clamp-2 text-sm text-muted-foreground">
                        {p.description}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline">
                          <Users size={12} className="mr-1" />
                          {p.members.length} members
                        </Badge>
                        {/* Global model accuracy — Team Lead only */}
                        {isTeamLead && (
                          <Badge
                            variant="outline"
                            className="mono-data text-emerald-500"
                          >
                            {formatPercent(latestAccuracy(p.id))}
                          </Badge>
                        )}
                        <Badge variant="outline" className="mono-data">
                          {p.config.attackType.replace(/_/g, " ")}
                        </Badge>
                      </div>
                      {pending ?
                        <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400">
                          Request Pending
                        </Badge>
                      : <Button
                          size="sm"
                          onClick={() => {
                            setRequestTarget(p);
                            setRequestMessage("");
                          }}
                        >
                          Request to Join
                        </Button>
                      }
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          }
        </TabsContent>

        {/* ── My Requests ─────────────────────── */}
        <TabsContent value="requests">
          {myRequests.length === 0 ?
            <EmptyState
              icon={ClipboardList}
              title="No requests"
              description="You haven't requested to join any projects yet."
            />
          : <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>Visibility</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Message</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {myRequests.map((req) => {
                    const project = allProjects.find(
                      (p) => p.id === req.projectId,
                    );
                    const statusColors = {
                      pending:
                        "bg-amber-500/10 text-amber-600 dark:text-amber-400",
                      approved:
                        "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
                      rejected:
                        "bg-rose-500/10 text-rose-600 dark:text-rose-400",
                    };
                    return (
                      <TableRow key={req.id}>
                        <TableCell className="font-medium">
                          {project?.name || req.projectId}
                        </TableCell>
                        <TableCell>
                          {project?.visibility === "private" ?
                            <Badge
                              variant="outline"
                              className="text-muted-foreground"
                            >
                              <LockKeyhole size={10} className="mr-1" /> Private
                            </Badge>
                          : <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                              <Globe size={10} className="mr-1" /> Public
                            </Badge>
                          }
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDistanceToNow(new Date(req.requestedAt), {
                            addSuffix: true,
                          })}
                        </TableCell>
                        <TableCell>
                          <Badge className={statusColors[req.status] || ""}>
                            {req.status.charAt(0).toUpperCase() +
                              req.status.slice(1)}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                          {req.message || "—"}
                        </TableCell>
                        <TableCell>
                          {req.status === "approved" && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                navigate(`/dashboard/projects/${req.projectId}`)
                              }
                            >
                              View Project
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          }
        </TabsContent>
      </Tabs>

      {/* ── Request to Join dialog ─────────── */}
      <Dialog
        open={!!requestTarget}
        onOpenChange={() => {
          setRequestTarget(null);
          setRequestMessage("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request to Join {requestTarget?.name}</DialogTitle>
            <DialogDescription>
              Your request will be sent to the project lead for approval.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Clients</span>
                <span className="mono-data">
                  {requestTarget?.config.numClients}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Attack</span>
                <span className="mono-data">
                  {requestTarget?.config.attackType.replace(/_/g, " ")}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Aggregator</span>
                <span className="mono-data">
                  {requestTarget?.config.aggregationMethod.replace(/_/g, " ")}
                </span>
              </div>
            </div>
            <div>
              <Label>Message (optional)</Label>
              <Input
                placeholder="Introduce yourself or explain your interest…"
                value={requestMessage}
                onChange={(e) => setRequestMessage(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRequestTarget(null);
                setRequestMessage("");
              }}
            >
              Cancel
            </Button>
            <Button onClick={() => handleSubmitRequest(requestTarget)}>
              Submit Request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Join with Code dialog ──────────── */}
      <Dialog open={codeDialogOpen} onOpenChange={resetCodeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Join with Invite Code</DialogTitle>
            <DialogDescription>
              Enter the 6-character code shared by a project lead.
            </DialogDescription>
          </DialogHeader>

          {!codeProject ?
            <div className="space-y-3">
              <Input
                placeholder="e.g. FX9K3R"
                value={inviteCode}
                onChange={(e) => {
                  setInviteCode(e.target.value.toUpperCase());
                  setCodeError("");
                }}
                maxLength={6}
                className="mono-data text-center text-lg tracking-widest"
              />
              {codeError && (
                <p className="text-sm text-destructive">{codeError}</p>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={resetCodeDialog}>
                  Cancel
                </Button>
                <Button
                  onClick={handleCodeLookup}
                  disabled={inviteCode.length !== 6}
                >
                  Look Up
                </Button>
              </DialogFooter>
            </div>
          : <div className="space-y-4">
              <Card>
                <CardContent className="space-y-2 p-4">
                  <div className="flex items-center gap-2">
                    <p className="font-medium">{codeProject.name}</p>
                    <Badge variant="outline" className="text-muted-foreground">
                      <LockKeyhole size={10} className="mr-1" /> Private
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {codeProject.description}
                  </p>
                  <div className="flex gap-2 text-xs text-muted-foreground">
                    <span>
                      Lead:{" "}
                      {codeProject.members.find((m) => m.role === "lead")
                        ?.userName || "—"}
                    </span>
                    <span>·</span>
                    <span>{codeProject.members.length} members</span>
                  </div>
                </CardContent>
              </Card>
              {hasPendingRequest(codeProject.id) ?
                <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400">
                  Request Already Pending
                </Badge>
              : <>
                  <div>
                    <Label>Message (optional)</Label>
                    <Input
                      placeholder="Introduce yourself…"
                      value={requestMessage}
                      onChange={(e) => setRequestMessage(e.target.value)}
                    />
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={resetCodeDialog}>
                      Cancel
                    </Button>
                    <Button onClick={handleCodeRequest}>Submit Request</Button>
                  </DialogFooter>
                </>
              }
            </div>
          }
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
