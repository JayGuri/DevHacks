import { useState } from "react";
import { toast } from "sonner";
import { Play, Pause, Download, RotateCcw, Lock } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfirmDialog from "@/components/dashboard/ConfirmDialog";
import { useStore } from "@/lib/store";
import { getAllProjects } from "@/lib/projectUtils";
import { useFeatureGate } from "@/hooks/useFeatureGate";

// fedavg is always available (Free tier base algorithm)
const FREE_AGGREGATORS = [
  { value: "fedavg", desc: "Standard federated averaging" },
];

// These require a Pro subscription
const PRO_AGGREGATORS = [
  { value: "trimmed_mean", desc: "Drop top/bottom k gradients" },
  { value: "coordinate_median", desc: "Per-coordinate median" },
  { value: "krum", desc: "Select closest gradient to centroid" },
  { value: "bulyan", desc: "Krum + trimmed mean combo" },
  { value: "reputation", desc: "SABD trust-weighted average" },
];

export default function ControlPanel({ fl, projectId }) {
  const store = useStore();
  const { canUseAdvancedAggregation, canExportMetrics } = useFeatureGate();
  const methodByProject = store.methodByProject;
  const roundsByProject = store.roundsByProject;
  const pushNotification = store.pushNotification;

  const projectName =
    getAllProjects(store).find((p) => p.id === projectId)?.name || projectId;

  // Available aggregators depend on subscription tier
  const availableAggregators = canUseAdvancedAggregation
    ? [...FREE_AGGREGATORS, ...PRO_AGGREGATORS]
    : FREE_AGGREGATORS;

  const currentMethod =
    methodByProject[projectId] ||
    fl.project?.config?.aggregationMethod ||
    (canUseAdvancedAggregation ? "trimmed_mean" : "fedavg");

  const [sabdLocal, setSabdLocal] = useState(
    fl.project?.config?.sabdAlpha ?? 0.5,
  );

  function handleExport() {
    const blob = new Blob([JSON.stringify(fl.allRounds, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `arfl-${projectId}-results.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Results exported");
  }

  function handleReset() {
    const store = useStore.getState();
    store.roundsByProject[projectId] = [];
    useStore.setState({ roundsByProject: { ...store.roundsByProject } });
    toast.warning("Simulation reset");
  }

  const desc = AGGREGATORS.find((a) => a.value === currentMethod)?.desc || "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-sm">Control Panel</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Aggregation method */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="metric-label text-muted-foreground">
              Aggregation Method
            </label>
            {!canUseAdvancedAggregation && (
              <Link
                to="/admin/billing"
                className="flex items-center gap-1 text-[10px] text-amber-500 hover:underline"
              >
                <Lock size={10} /> Upgrade for Multi-Krum, Trimmed Mean…
              </Link>
            )}
          </div>
          <Select
            value={currentMethod}
            onValueChange={(v) => {
              fl.setAggregationMethod(v);
              pushNotification({
                type: "config",
                message: `Aggregation method changed to ${v.replace(/_/g, " ")} in ${projectName}`,
                projectId,
              });
              toast.info(`Aggregation → ${v.replace(/_/g, " ")}`);
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableAggregators.map((a) => (
                <SelectItem key={a.value} value={a.value}>
                  {a.value.replace(/_/g, " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            {availableAggregators.find((a) => a.value === currentMethod)?.desc || ""}
          </p>
        </div>

        {/* SABD Alpha */}
        <div className="space-y-1">
          <label className="metric-label text-muted-foreground">
            SABD Alpha
          </label>
          <Slider
            min={0}
            max={1}
            step={0.1}
            value={[sabdLocal]}
            onValueChange={([v]) => setSabdLocal(v)}
          />
          <Badge variant="outline" className="mono-data">
            α = {sabdLocal.toFixed(1)}
          </Badge>
        </div>

        {/* Pause / Resume */}
        <Button
          className="w-full"
          variant={fl.isRunning ? "outline" : "default"}
          onClick={() => (fl.isRunning ? fl.pause() : fl.resume())}
        >
          {fl.isRunning ?
            <>
              <Pause size={14} className="mr-2" /> Pause Simulation
            </>
          : <>
              <Play size={14} className="mr-2" />
              <span className="relative mr-2 flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
              </span>
              Resume Simulation
            </>
          }
        </Button>

        {/* Round progress */}
        <div className="space-y-1">
          <p className="mono-data text-sm">
            Round {fl.currentRound} / {fl.totalRounds}
          </p>
          <Progress
            value={(fl.currentRound / fl.totalRounds) * 100}
            className="h-2"
          />
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="flex-1"
            onClick={canExportMetrics ? handleExport : undefined}
            disabled={!canExportMetrics}
            title={canExportMetrics ? "Export metrics as JSON" : "Pro subscription required"}
          >
            {canExportMetrics ? (
              <><Download size={14} className="mr-1" /> Export JSON</>
            ) : (
              <><Lock size={14} className="mr-1" /> Export (Pro)</>
            )}
          </Button>
          <ConfirmDialog
            trigger={
              <Button variant="ghost" className="flex-1 text-destructive">
                <RotateCcw size={14} className="mr-1" /> Reset
              </Button>
            }
            title="Reset Simulation"
            description="This will clear all rounds and reset to round 0. Continue?"
            actionLabel="Reset"
            variant="destructive"
            onConfirm={handleReset}
          />
        </div>
      </CardContent>
    </Card>
  );
}
