import { useState } from "react";
import { motion } from "framer-motion";
import { cn, getTrustBg, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";

const FILTERS = ["All", "Honest", "Slow", "Byzantine", "Blocked"];

function statusBadge(status) {
  const map = {
    ACTIVE: "border-emerald-500 text-emerald-600 dark:text-emerald-400",
    SLOW: "border-amber-500 text-amber-600 dark:text-amber-400",
    BYZANTINE: "border-rose-500 text-rose-600 dark:text-rose-400",
    BLOCKED: "border-muted-foreground text-muted-foreground",
  };
  return (
    <Badge variant="outline" className={map[status] || ""}>
      {status}
    </Badge>
  );
}

function typeLabel(node) {
  if (node.isByzantine) return <span className="text-rose-500">Byzantine</span>;
  if (node.isSlow) return <span className="text-amber-500">Slow</span>;
  return <span className="text-emerald-500">Honest</span>;
}

function trustIndicatorClass(trust) {
  if (trust >= 0.7) return "bg-emerald-500";
  if (trust >= 0.4) return "bg-amber-500";
  return "bg-rose-500";
}

function filterNodes(nodes, filter) {
  if (filter === "All") return nodes;
  if (filter === "Honest") return nodes.filter((n) => !n.isByzantine && !n.isSlow && !n.isBlocked);
  if (filter === "Slow") return nodes.filter((n) => n.isSlow && !n.isBlocked);
  if (filter === "Byzantine") return nodes.filter((n) => n.isByzantine && !n.isBlocked);
  if (filter === "Blocked") return nodes.filter((n) => n.isBlocked);
  return nodes;
}

function StatPill({ color, count, label }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5">
      <span className={cn("h-2.5 w-2.5 rounded-full", color)} />
      <span className="font-display text-lg font-bold">{count}</span>
      <span className="metric-label text-muted-foreground">{label}</span>
    </div>
  );
}

export default function NodeMatrix({
  nodes,
  viewMode,
  isAdmin,
  onBlock,
  onUnblock,
}) {
  const [filter, setFilter] = useState("All");

  const counts = {
    active: nodes.filter((n) => n.status === "ACTIVE").length,
    slow: nodes.filter((n) => n.status === "SLOW").length,
    byzantine: nodes.filter((n) => n.status === "BYZANTINE").length,
    blocked: nodes.filter((n) => n.isBlocked).length,
  };

  const filtered = filterNodes(nodes, filter);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {viewMode === "simple" ? (
        <div className="flex flex-wrap gap-3">
          <StatPill color="bg-emerald-500" count={counts.active} label="Active" />
          <StatPill color="bg-amber-500" count={counts.slow} label="Slow" />
          <StatPill color="bg-rose-500" count={counts.byzantine} label="Byzantine" />
          <StatPill color="bg-muted-foreground" count={counts.blocked} label="Blocked" />
        </div>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                  filter === f
                    ? "border border-primary/30 bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent"
                )}
              >
                {f}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Node</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Trust</TableHead>
                  <TableHead>Cos. Dist</TableHead>
                  <TableHead>Staleness</TableHead>
                  <TableHead>Status</TableHead>
                  {isAdmin && <TableHead>Action</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((node, index) => (
                  <motion.tr
                    key={node.nodeId}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, delay: index * 0.04 }}
                    className={cn(
                      "border-b border-border",
                      node.isByzantine && !node.isBlocked && "bg-rose-500/5",
                      node.isBlocked && "opacity-50"
                    )}
                  >
                    <TableCell className="mono-data font-medium">
                      {node.displayId}
                    </TableCell>
                    <TableCell>{typeLabel(node)}</TableCell>
                    <TableCell>
                      <div className="w-24 space-y-1">
                        <Progress
                          value={node.trust * 100}
                          className="h-1.5"
                          indicatorClassName={trustIndicatorClass(node.trust)}
                        />
                        <span className="mono-data text-xs text-muted-foreground">
                          {formatPercent(node.trust * 100)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell
                      className={cn(
                        "mono-data text-sm",
                        node.cosineDistance > 0.45
                          ? "text-rose-500"
                          : "text-muted-foreground"
                      )}
                    >
                      {node.cosineDistance.toFixed(3)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{node.staleness}R</Badge>
                    </TableCell>
                    <TableCell>{statusBadge(node.status)}</TableCell>
                    {isAdmin && (
                      <TableCell>
                        {node.isBlocked ? (
                          <ConfirmDialog
                            trigger={
                              <Button size="sm" variant="ghost">
                                Unblock
                              </Button>
                            }
                            title="Unblock Node"
                            description={`Restore ${node.displayId} to active participation?`}
                            actionLabel="Unblock"
                            onConfirm={() => onUnblock(node.nodeId)}
                          />
                        ) : (
                          <ConfirmDialog
                            trigger={
                              <Button size="sm" variant="outline">
                                Block
                              </Button>
                            }
                            title="Block Node"
                            description={`Remove ${node.displayId} from training? This node will stop contributing updates.`}
                            actionLabel="Block"
                            variant="destructive"
                            onConfirm={() => onBlock(node.nodeId)}
                          />
                        )}
                      </TableCell>
                    )}
                  </motion.tr>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </motion.div>
  );
}
