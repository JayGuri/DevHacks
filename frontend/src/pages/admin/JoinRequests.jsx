import { useState, useEffect } from "react";
import { toast } from "sonner";
import { CheckCircle, XCircle, Inbox } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/lib/store";
import { MOCK_USERS } from "@/lib/mockData";
import { USE_MOCK } from "@/lib/config";
import {
  apiListJoinRequests,
  apiApproveJoinRequest,
  apiRejectJoinRequest,
  apiListProjects,
} from "@/lib/api";
import { getAllProjects, getUserManagedProjects } from "@/lib/projectUtils";
import AppLayout from "@/components/layout/AppLayout";
import EmptyState from "@/components/dashboard/EmptyState";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function JoinRequests() {
  const { currentUser } = useAuth();
  const store = useStore();
  const approveRequest = store.approveRequest;
  const rejectRequest = store.rejectRequest;
  const pushNotification = store.pushNotification;
  const pushActivity = store.pushActivity;

  const allProjects = getAllProjects(store);
  const managedProjects = getUserManagedProjects(currentUser?.id, store);
  const managedIds = managedProjects.map((p) => p.id);

  const allRequests =
    USE_MOCK ?
      store.joinRequests.filter((r) => managedIds.includes(r.projectId))
    : store.fetchedJoinRequests.filter((r) => managedIds.includes(r.projectId));

  // Fetch join requests and projects when not using mock
  useEffect(() => {
    if (!USE_MOCK) {
      apiListProjects()
        .then((data) => store.setProjects(data))
        .catch(() => {});
      apiListJoinRequests()
        .then((data) => store.setFetchedJoinRequests(data))
        .catch((err) => console.error("Failed to fetch join requests:", err));
    }
  }, []);

  const [filterProject, setFilterProject] = useState("all");

  const filtered =
    filterProject === "all" ? allRequests : (
      allRequests.filter((r) => r.projectId === filterProject)
    );

  const pending = filtered.filter((r) => r.status === "pending");
  const approved = filtered.filter((r) => r.status === "approved");
  const rejected = filtered.filter((r) => r.status === "rejected");

  function projectName(pid) {
    return allProjects.find((p) => p.id === pid)?.name || pid;
  }

  function projectVisibility(pid) {
    return allProjects.find((p) => p.id === pid)?.visibility || "public";
  }

  function resolverName(uid) {
    if (!uid) return "—";
    if (!USE_MOCK) return uid; // In API mode we just show the ID (could be enhanced)
    return MOCK_USERS.find((u) => u.id === uid)?.name || uid;
  }

  async function handleApprove(req) {
    if (!USE_MOCK) {
      try {
        const updated = await apiApproveJoinRequest(req.id);
        store.setFetchedJoinRequests(
          store.fetchedJoinRequests.map((r) => (r.id === req.id ? updated : r)),
        );
        toast.success(`${req.userName} approved`);
      } catch (err) {
        toast.error(err.message || "Failed to approve");
      }
      return;
    }
    // Mock mode
    approveRequest(req.id, currentUser.id);
    const pName = projectName(req.projectId);
    pushNotification({
      type: "request_approved",
      targetUserId: req.userId,
      message: `Your request to join "${pName}" was approved.`,
      projectId: req.projectId,
    });
    pushActivity({
      type: "join",
      message: `${req.userName} joined ${pName}`,
      userId: req.userId,
      timestamp: new Date().toISOString(),
      projectId: req.projectId,
    });
    toast.success(`${req.userName} approved for ${pName}`);
  }

  async function handleReject(req) {
    if (!USE_MOCK) {
      try {
        const updated = await apiRejectJoinRequest(req.id);
        store.setFetchedJoinRequests(
          store.fetchedJoinRequests.map((r) => (r.id === req.id ? updated : r)),
        );
        toast.info("Request rejected");
      } catch (err) {
        toast.error(err.message || "Failed to reject");
      }
      return;
    }
    // Mock mode
    rejectRequest(req.id, currentUser.id);
    const pName = projectName(req.projectId);
    pushNotification({
      type: "request_rejected",
      targetUserId: req.userId,
      message: `Your request to join "${pName}" was not approved.`,
      projectId: req.projectId,
    });
    toast.info("Request rejected");
  }

  const filterBar = (
    <div className="mb-4">
      <Select value={filterProject} onValueChange={setFilterProject}>
        <SelectTrigger className="w-48">
          <SelectValue placeholder="Filter by project" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Projects</SelectItem>
          {managedProjects.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  function visibilityBadge(pid) {
    const vis = projectVisibility(pid);
    return vis === "private" ?
        <Badge variant="outline" className="text-muted-foreground">
          Private
        </Badge>
      : <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          Public
        </Badge>;
  }

  return (
    <AppLayout title="Join Requests">
      <Tabs defaultValue="pending">
        <TabsList className="mb-4">
          <TabsTrigger value="pending">Pending ({pending.length})</TabsTrigger>
          <TabsTrigger value="approved">
            Approved ({approved.length})
          </TabsTrigger>
          <TabsTrigger value="rejected">
            Rejected ({rejected.length})
          </TabsTrigger>
        </TabsList>

        {/* Pending */}
        <TabsContent value="pending">
          {filterBar}
          {pending.length === 0 ?
            <EmptyState
              icon={Inbox}
              title="No pending requests"
              description="All caught up."
            />
          : <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Requester</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Visibility</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Message</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pending.map((req) => (
                    <TableRow key={req.id}>
                      <TableCell className="font-medium">
                        {req.userName}
                      </TableCell>
                      <TableCell className="mono-data text-xs">
                        {req.userEmail}
                      </TableCell>
                      <TableCell>{projectName(req.projectId)}</TableCell>
                      <TableCell>{visibilityBadge(req.projectId)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(req.requestedAt), {
                          addSuffix: true,
                        })}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                        {req.message || "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <ConfirmDialog
                            trigger={
                              <Button
                                size="sm"
                                className="bg-emerald-600 text-white hover:bg-emerald-700"
                              >
                                <CheckCircle size={14} className="mr-1" />{" "}
                                Approve
                              </Button>
                            }
                            title="Approve Request"
                            description={`Allow ${req.userName} to join ${projectName(req.projectId)}?`}
                            confirmLabel="Approve"
                            onConfirm={() => handleApprove(req)}
                          />
                          <ConfirmDialog
                            trigger={
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-rose-500 hover:text-rose-600"
                              >
                                <XCircle size={14} className="mr-1" /> Reject
                              </Button>
                            }
                            title="Reject Request"
                            description={`Reject ${req.userName}'s request to join ${projectName(req.projectId)}?`}
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
          }
        </TabsContent>

        {/* Approved */}
        <TabsContent value="approved">
          {filterBar}
          {approved.length === 0 ?
            <EmptyState
              icon={Inbox}
              title="No approved requests"
              description="Approved requests will appear here."
            />
          : <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Requester</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Visibility</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Resolved</TableHead>
                    <TableHead>By</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {approved.map((req) => (
                    <TableRow key={req.id}>
                      <TableCell className="font-medium">
                        {req.userName}
                      </TableCell>
                      <TableCell className="mono-data text-xs">
                        {req.userEmail}
                      </TableCell>
                      <TableCell>{projectName(req.projectId)}</TableCell>
                      <TableCell>{visibilityBadge(req.projectId)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(req.requestedAt), {
                          addSuffix: true,
                        })}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {req.resolvedAt ?
                          formatDistanceToNow(new Date(req.resolvedAt), {
                            addSuffix: true,
                          })
                        : "—"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {resolverName(req.resolvedBy)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          }
        </TabsContent>

        {/* Rejected */}
        <TabsContent value="rejected">
          {filterBar}
          {rejected.length === 0 ?
            <EmptyState
              icon={Inbox}
              title="No rejected requests"
              description="Rejected requests will appear here."
            />
          : <div className="overflow-x-auto rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Requester</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Project</TableHead>
                    <TableHead>Visibility</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Resolved</TableHead>
                    <TableHead>By</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rejected.map((req) => (
                    <TableRow key={req.id}>
                      <TableCell className="font-medium">
                        {req.userName}
                      </TableCell>
                      <TableCell className="mono-data text-xs">
                        {req.userEmail}
                      </TableCell>
                      <TableCell>{projectName(req.projectId)}</TableCell>
                      <TableCell>{visibilityBadge(req.projectId)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(req.requestedAt), {
                          addSuffix: true,
                        })}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {req.resolvedAt ?
                          formatDistanceToNow(new Date(req.resolvedAt), {
                            addSuffix: true,
                          })
                        : "—"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {resolverName(req.resolvedBy)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          }
        </TabsContent>
      </Tabs>
    </AppLayout>
  );
}
