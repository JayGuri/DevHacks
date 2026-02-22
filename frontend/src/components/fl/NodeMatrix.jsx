import { useState, useRef, useEffect, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn, getTrustBg, formatPercent } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import AnimatedNumber from "@/components/ui/AnimatedNumber";
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

const statusBadge = (status) => {
  const map = {
    ACTIVE: "badge-active",
    SLOW: "badge-slow",
    BYZANTINE: "badge-byzantine",
    BLOCKED: "badge-blocked",
  };
  return <span className={cn(map[status] || "badge-custom")}>{status}</span>;
};

const typeLabel = (node) => {
  if (node.isByzantine)
    return (
      <span className="text-rose-500 font-mono text-[11px] font-bold">
        BYZANTINE
      </span>
    );
  if (node.isSlow)
    return (
      <span className="text-amber-500 font-mono text-[11px] font-bold">
        SLOW
      </span>
    );
  return (
    <span className="text-emerald-500 font-mono text-[11px] font-bold">
      HONEST
    </span>
  );
};

const trustIndicatorClass = (trust) => {
  if (trust >= 0.7)
    return "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]";
  if (trust >= 0.4) return "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]";
  return "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]";
};

const filterNodes = (nodes, filter) => {
  if (filter === "All") return nodes;
  if (filter === "Honest")
    return nodes.filter((n) => !n.isByzantine && !n.isSlow && !n.isBlocked);
  if (filter === "Slow") return nodes.filter((n) => n.isSlow && !n.isBlocked);
  if (filter === "Byzantine")
    return nodes.filter((n) => n.isByzantine && !n.isBlocked);
  if (filter === "Blocked") return nodes.filter((n) => n.isBlocked);
  return nodes;
};

const NodeMatrix = memo(({ isAdmin, onBlock, onUnblock }) => {
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
      <div className="mb-6 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-full px-4 py-1.5 text-[11px] font-mono tracking-wider uppercase transition-all duration-200 border",
              filter === f ?
                "bg-primary text-primary-foreground border-primary shadow-lg shadow-primary/20"
              : "bg-card text-muted-foreground border-border hover:border-primary/50",
            )}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="card-base overflow-x-auto">
        <Table>
          <TableHeader className="table-header">
            <TableRow>
              <TableHead>Node ID</TableHead>
              <TableHead>Entity Type</TableHead>
              <TableHead>Reputation Trust</TableHead>
              <TableHead>Cos. Entropy</TableHead>
              <TableHead>Staleness</TableHead>
              <TableHead>Operational Status</TableHead>
              {isAdmin && (
                <TableHead className="text-right">Orchestration</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            <AnimatePresence initial={false} mode="popLayout">
              {filtered.map((node, index) => (
                <NodeRow
                  key={node.nodeId}
                  node={node}
                  index={index}
                  isAdmin={isAdmin}
                  onBlock={onBlock}
                  onUnblock={onUnblock}
                />
              ))}
            </AnimatePresence>
          </TableBody>
        </Table>
      </div>
    </motion.div>
  );
});

const NodeRow = memo(({ node, index, isAdmin, onBlock, onUnblock }) => {
  const prevNodeRef = useRef(node);
  const [flashClass, setFlashClass] = useState("");
  const [statusPulse, setStatusPulse] = useState("");

  useEffect(() => {
    const prev = prevNodeRef.current;
    if (prev.trust !== node.trust) {
      setFlashClass("animate-row-flash");
      const timer = setTimeout(() => setFlashClass(""), 500);
      return () => clearTimeout(timer);
    }
    if (prev.status !== node.status && node.status === "BYZANTINE") {
      setStatusPulse("animate-rose-flash");
      const timer = setTimeout(() => setStatusPulse(""), 1600);
      return () => clearTimeout(timer);
    }
    prevNodeRef.current = node;
  }, [node]);

  return (
    <motion.tr
      layout
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.15 } }}
      className={cn(
        "table-row group h-16",
        node.isByzantine && !node.isBlocked && "bg-rose-500/[0.02]",
        node.isBlocked && "opacity-40 grayscale",
        flashClass,
        statusPulse,
      )}
    >
      <TableCell className="mono-data font-bold text-primary/80">
        {node.displayId}
      </TableCell>
      <TableCell>{typeLabel(node)}</TableCell>
      <TableCell>
        <div className="w-32 space-y-1.5">
          <Progress
            value={node.trust * 100}
            className="h-1 bg-muted rounded-full overflow-hidden"
            indicatorClassName={cn(
              "transition-all duration-500",
              trustIndicatorClass(node.trust),
            )}
          />
          <div className="mono-data text-[10px] text-muted-foreground flex justify-between items-center pr-2">
            <span>SCORE</span>
            <AnimatedNumber value={node.trust * 100} decimals={2} suffix="%" />
          </div>
        </div>
      </TableCell>
      <TableCell
        className={cn(
          "mono-data text-xs font-semibold",
          node.cosineDistance > 0.45 ?
            "text-rose-500"
          : "text-muted-foreground opacity-80",
        )}
      >
        <AnimatedNumber value={node.cosineDistance} decimals={4} />
      </TableCell>
      <TableCell>
        <span className="mono-data text-[11px] bg-muted/50 px-2 py-0.5 rounded border border-border/40">
          {node.staleness}R
        </span>
      </TableCell>
      <TableCell>
        <motion.div
          animate={statusPulse ? { scale: [1, 1.15, 1] } : {}}
          transition={{ duration: 0.4 }}
        >
          {statusBadge(node.status)}
        </motion.div>
      </TableCell>
      {isAdmin && (
        <TableCell className="text-right">
          {node.isBlocked ?
            <ConfirmDialog
              trigger={
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 text-[11px] metric-label text-cyan-600 hover:text-cyan-700 hover:bg-cyan-500/10 rounded-full"
                >
                  Unblock Entity
                </Button>
              }
              title="Restore Participation"
              description={`Re-integrate ${node.displayId} into the training federation? Trust scores will resume calculation.`}
              actionLabel="Confirm Restore"
              onConfirm={() => onUnblock(node.nodeId)}
            />
          : <ConfirmDialog
              trigger={
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-[11px] metric-label border-rose-500/20 text-rose-600 hover:bg-rose-500/5 rounded-full px-4"
                >
                  Sanction Node
                </Button>
              }
              title="Isolate Byzantine Entity"
              description={`Revoke all training privileges for ${node.displayId}? This will immediately discard its gradients from the aggregation buffer.`}
              actionLabel="Apply Sanction"
              variant="destructive"
              onConfirm={() => onBlock(node.nodeId)}
            />
          }
        </TableCell>
      )}
    </motion.tr>
  );
});

export default NodeMatrix;
