/**
 * ContributorWorkspace — FL model submission interface for contributors.
 *
 * Workflow:
 *   1. Write / paste / upload local training code (Python template provided)
 *   2. Click "Run Local Test" to simulate running the code and producing
 *      gradient updates (in a real deployment the user would run this locally
 *      and paste the JSON output into the Gradients tab)
 *   3. Review the gradient statistics
 *   4. Click "Submit to Pipeline" — gradients pass through:
 *         L2 Norm Clipping → Zero-Sum Masking → Aggregation → Global Model
 *
 * Deliberately hides ALL server-side metrics (trust scores, SABD, node data).
 */

import { useState, useRef, useCallback } from "react";
import {
  Upload,
  Play,
  Send,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  FileCode2,
  ChevronDown,
  ChevronUp,
  Info,
  Code2,
  ClipboardPaste,
  History,
  Zap,
  Lock,
  ArrowRight,
  Activity,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { apiSubmitUpdate } from "@/lib/api";
import { USE_MOCK } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// ── Default training code template ──────────────────────────────────────────

const CODE_TEMPLATE = `# Federated Learning — Local Training Script
# Run this on your local machine with your private dataset.
# After training, submit the resulting gradients via the "Gradients" tab.
#
# NOTE: Only gradient deltas are sent — your raw data NEVER leaves your machine.

import torch
import torch.nn as nn
import torch.optim as optim
import json

# ── 1. Define your local model (must match the global architecture) ──────────
class LocalModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1  = nn.Conv2d(1, 32, 5)
        self.conv2  = nn.Conv2d(32, 64, 5)
        self.fc1    = nn.Linear(64 * 4 * 4, 128)
        self.fc2    = nn.Linear(128, 10)

    def forward(self, x):
        x = torch.relu(self.conv1(x))
        x = torch.max_pool2d(x, 2)
        x = torch.relu(self.conv2(x))
        x = torch.max_pool2d(x, 2)
        x = x.view(x.size(0), -1)
        x = torch.relu(self.fc1(x))
        return self.fc2(x)

# ── 2. Local training loop ───────────────────────────────────────────────────
def train_local(model, dataloader, epochs=3, lr=0.01):
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(epochs):
        for x, y in dataloader:
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()

    return model

# ── 3. Extract gradient deltas (send THESE, not raw data) ────────────────────
def extract_gradients(model_before, model_after):
    grads = {}
    for (name, p_before), (_, p_after) in zip(
        model_before.named_parameters(),
        model_after.named_parameters()
    ):
        delta = (p_after - p_before).detach().cpu().flatten().tolist()
        grads[name] = delta
    return grads

# ── 4. Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Load your LOCAL dataset here (never shared with the server)
    # dataloader = DataLoader(your_local_dataset, batch_size=32, shuffle=True)

    # Download the current global model weights from the project page
    global_weights = torch.load("global_model.pt")

    model_before = LocalModel()
    model_before.load_state_dict(global_weights)

    model_after = LocalModel()
    model_after.load_state_dict(global_weights)

    # Train on local data
    model_after = train_local(model_after, dataloader, epochs=3)

    # Extract gradient deltas
    gradients = extract_gradients(model_before, model_after)

    # Export as JSON — paste this into the "Gradients" tab in the UI
    print(json.dumps(gradients, indent=2))
`;

// ── Gradient generator (simulates what local training produces) ──────────────

function generateMockGradients(numLayers = 8) {
  const layerDefs = [
    { name: "conv1.weight", size: 800 },
    { name: "conv1.bias", size: 32 },
    { name: "conv2.weight", size: 51200 },
    { name: "conv2.bias", size: 64 },
    { name: "fc1.weight", size: 131072 },
    { name: "fc1.bias", size: 128 },
    { name: "fc2.weight", size: 1280 },
    { name: "fc2.bias", size: 10 },
  ].slice(0, numLayers);

  const grads = {};
  for (const { name, size } of layerDefs) {
    // Use smaller representation — frontend submit only sends a sample
    const sampleSize = Math.min(size, 60);
    grads[name] = Array.from(
      { length: sampleSize },
      () => (Math.random() - 0.5) * 0.02,
    );
  }
  return grads;
}

function computeL2Norm(gradients) {
  let sumSq = 0;
  for (const vals of Object.values(gradients)) {
    for (const v of vals) sumSq += v * v;
  }
  return Math.sqrt(sumSq);
}

// ── Pipeline stage component ─────────────────────────────────────────────────

const PIPELINE_STAGES = [
  {
    id: "local",
    label: "Local Training",
    icon: Code2,
    desc: "Runs on your machine only",
  },
  {
    id: "l2",
    label: "L2 Norm Clip",
    icon: Zap,
    desc: "Bounds gradient influence",
  },
  {
    id: "mask",
    label: "Zero-Sum Mask",
    icon: Lock,
    desc: "Secure aggregation layer",
  },
  {
    id: "agg",
    label: "Aggregation",
    icon: Activity,
    desc: "FedAvg / Trimmed Mean",
  },
  {
    id: "model",
    label: "Global Model",
    icon: CheckCircle2,
    desc: "Updated global weights",
  },
];

function PipelineVisualizer({ activeStage }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/60">
        FL Submission Pipeline
      </p>
      <div className="flex items-stretch gap-0">
        {PIPELINE_STAGES.map((stage, i) => {
          const Icon = stage.icon;
          const isActive = activeStage === stage.id;
          const isDone =
            activeStage &&
            PIPELINE_STAGES.findIndex((s) => s.id === activeStage) > i;

          return (
            <div key={stage.id} className="flex items-center flex-1 min-w-0">
              <div
                className={cn(
                  "flex-1 flex flex-col items-center gap-1 rounded-lg px-1.5 py-2 text-center transition-all duration-500",
                  isActive && "bg-primary/15 ring-1 ring-primary/40",
                  isDone && "bg-emerald-500/10",
                  !isActive && !isDone && "bg-muted/20",
                )}
              >
                <div
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full transition-colors",
                    isActive && "bg-primary text-primary-foreground",
                    isDone && "bg-emerald-500 text-white",
                    !isActive && !isDone && "bg-muted text-muted-foreground",
                  )}
                >
                  {isDone ?
                    <CheckCircle2 size={12} />
                  : <Icon size={12} />}
                </div>
                <p
                  className={cn(
                    "text-[9px] font-medium leading-tight truncate w-full",
                    isActive && "text-primary",
                    isDone && "text-emerald-600 dark:text-emerald-400",
                    !isActive && !isDone && "text-muted-foreground",
                  )}
                >
                  {stage.label}
                </p>
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <ArrowRight
                  size={12}
                  className={cn(
                    "shrink-0 mx-0.5 transition-colors",
                    isDone ? "text-emerald-500" : "text-muted-foreground/30",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Gradient statistics sub-component ────────────────────────────────────────

function GradientStats({ gradients, clipFactor, clippedNorm, l2Norm }) {
  const [expanded, setExpanded] = useState(false);
  const layerNames = Object.keys(gradients);

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">
          Gradient Statistics
        </span>
        <button
          onClick={() => setExpanded((e) => !e)}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          {expanded ?
            <ChevronUp size={14} />
          : <ChevronDown size={14} />}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <p className="mono-data text-sm font-bold text-foreground">
            {l2Norm.toFixed(4)}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">L2 Norm</p>
        </div>
        <div className="text-center">
          <p className="mono-data text-sm font-bold text-emerald-500">
            {clippedNorm.toFixed(4)}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            Clipped Norm
          </p>
        </div>
        <div className="text-center">
          <p className="mono-data text-sm font-bold text-primary">
            {(clipFactor * 100).toFixed(1)}%
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Retained</p>
        </div>
      </div>

      {clipFactor < 1.0 && (
        <div className="flex items-start gap-2 rounded-md bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-600 dark:text-amber-400">
          <Info size={12} className="shrink-0 mt-0.5" />
          Gradients were clipped to the L2 norm budget. This is normal and
          protects model integrity.
        </div>
      )}

      {expanded && (
        <div className="space-y-1 pt-1">
          {layerNames.map((layer) => {
            const vals = gradients[layer];
            const max = Math.max(...vals.map(Math.abs));
            const paramCount = vals.length;
            return (
              <div key={layer} className="flex items-center gap-2">
                <span className="mono-data w-32 truncate text-[10px] text-muted-foreground">
                  {layer}
                </span>
                <Progress
                  value={Math.min(100, (max / 0.02) * 100)}
                  className="flex-1 h-1"
                />
                <span className="mono-data w-16 text-right text-[10px] text-muted-foreground">
                  {paramCount.toLocaleString()} params
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Submission history log ────────────────────────────────────────────────────

function SubmissionHistory({ history }) {
  if (!history.length) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <History size={13} />
          Submission History
          <Badge variant="outline" className="ml-auto text-[10px]">
            {history.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y divide-border max-h-48 overflow-y-auto">
          {[...history].reverse().map((entry, i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-4 py-2.5 text-[11px]"
            >
              <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <span className="text-muted-foreground">
                  Round{" "}
                  <span className="mono-data font-medium text-foreground">
                    {entry.round ?? "—"}
                  </span>
                </span>
                {entry.l2Norm != null && (
                  <span className="ml-3 text-muted-foreground">
                    L2{" "}
                    <span className="mono-data font-medium text-foreground">
                      {Number(entry.l2Norm).toFixed(4)}
                    </span>
                  </span>
                )}
              </div>
              <span className="text-muted-foreground whitespace-nowrap">
                {entry.submittedAt}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Line-numbered code editor ─────────────────────────────────────────────────

function LineNumberedEditor({ value, onChange }) {
  const gutterRef = useRef(null);
  const lines = value.split("\n");

  function handleScroll(e) {
    if (gutterRef.current) {
      gutterRef.current.scrollTop = e.target.scrollTop;
    }
  }

  return (
    <div className="flex rounded-b-lg overflow-hidden border-t border-border bg-[#0d1117]">
      {/* Line-number gutter — overflow hidden, scroll driven by textarea */}
      <div
        ref={gutterRef}
        className="select-none overflow-hidden shrink-0 py-4 pl-3 pr-2 text-right font-mono text-[11px] leading-relaxed text-[#6e7681] bg-[#0d1117] border-r border-[#21262d] min-w-[2.5rem]"
        aria-hidden="true"
        style={{ height: "288px" }}
      >
        {lines.map((_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>

      {/* Editable code area */}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={handleScroll}
        spellCheck={false}
        className={cn(
          "flex-1 resize-none bg-[#0d1117]",
          "px-3 py-4 font-mono text-[12px] leading-relaxed text-[#c9d1d9]",
          "focus:outline-none focus:ring-0",
        )}
        style={{ height: "288px" }}
      />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ContributorWorkspace({
  projectId,
  nodeId,
  trainingStatus,
  currentRound,
}) {
  const [editorTab, setEditorTab] = useState("code"); // "code" | "gradients"
  const [code, setCode] = useState(CODE_TEMPLATE);
  const [gradientJson, setGradientJson] = useState("");
  const [gradients, setGradients] = useState(null);
  const [gradientStats, setGradientStats] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [isComputing, setIsComputing] = useState(false);
  const [pipelineStage, setPipelineStage] = useState(null);
  const [submissionHistory, setSubmissionHistory] = useState([]);
  const fileInputRef = useRef(null);
  const jsonInputRef = useRef(null);

  const isActive = trainingStatus === "running" || trainingStatus === "paused";

  // ── Compute gradients (simulate local training output) ───────────────────
  const handleCompute = useCallback(async () => {
    setIsComputing(true);
    setGradients(null);
    setGradientStats(null);
    setPipelineStage("local");

    await new Promise((r) => setTimeout(r, 1400 + Math.random() * 600));

    const g = generateMockGradients();
    const l2 = computeL2Norm(g);
    const maxNorm = 1.0;
    const clipFactor = Math.min(1.0, maxNorm / Math.max(l2, 1e-8));
    const clippedNorm = l2 * clipFactor;

    setGradients(g);
    setGradientStats({ l2Norm: l2, clipFactor, clippedNorm });
    setIsComputing(false);
    setPipelineStage(null);
    toast.success("Gradients computed — ready to submit");
  }, []);

  // ── Parse gradients from JSON textarea ───────────────────────────────────
  const handleParseJson = useCallback(() => {
    try {
      const parsed = JSON.parse(gradientJson.trim());
      if (typeof parsed !== "object" || Array.isArray(parsed)) {
        toast.error('Expected a JSON object like {"layer": [values...]}');
        return;
      }
      const l2 = computeL2Norm(parsed);
      const maxNorm = 1.0;
      const clipFactor = Math.min(1.0, maxNorm / Math.max(l2, 1e-8));
      const clippedNorm = l2 * clipFactor;

      setGradients(parsed);
      setGradientStats({ l2Norm: l2, clipFactor, clippedNorm });
      toast.success("Gradients loaded from JSON");
    } catch {
      toast.error("Invalid JSON — check the format and try again");
    }
  }, [gradientJson]);

  // ── Upload a .py file into the code editor ────────────────────────────────
  function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".py") && !file.name.endsWith(".txt")) {
      toast.error("Only .py or .txt files are supported");
      return;
    }
    const reader = new FileReader();
    reader.onload = (evt) => {
      setCode(evt.target.result);
      setEditorTab("code");
      toast.success(`Loaded ${file.name}`);
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  // ── Upload a JSON gradient file ───────────────────────────────────────────
  function handleJsonUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      setGradientJson(evt.target.result);
      setEditorTab("gradients");
      toast.success(
        `Loaded ${file.name} — click "Parse Gradients" to validate`,
      );
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  // ── Submit gradients to the FL pipeline ──────────────────────────────────
  async function handleSubmit() {
    if (!gradients) {
      toast.error("Compute or paste gradients first");
      return;
    }
    if (!isActive) {
      toast.error(
        "Training is not active. Wait for the project lead to start training.",
      );
      return;
    }

    setSubmitting(true);
    try {
      // Animate through pipeline stages
      setPipelineStage("local");
      await new Promise((r) => setTimeout(r, 300));
      setPipelineStage("l2");
      await new Promise((r) => setTimeout(r, 300));
      setPipelineStage("mask");
      await new Promise((r) => setTimeout(r, 300));
      setPipelineStage("agg");

      let result;
      if (USE_MOCK) {
        await new Promise((r) => setTimeout(r, 600));
        result = {
          status: "accepted",
          round: currentRound || 1,
          l2Norm: gradientStats?.l2Norm?.toFixed(6),
          clippedNorm: gradientStats?.clippedNorm?.toFixed(6),
          clipFactor: gradientStats?.clipFactor?.toFixed(4),
          message: "Gradient update accepted and queued for aggregation.",
        };
      } else {
        result = await apiSubmitUpdate(projectId, {
          nodeId: nodeId || "unknown",
          gradients,
          dataSize: 100,
          round: currentRound,
        });
      }

      setPipelineStage("model");
      await new Promise((r) => setTimeout(r, 400));

      const record = {
        ...result,
        submittedAt: new Date().toLocaleTimeString(),
        round: result.round ?? currentRound,
      };
      setSubmissionHistory((prev) => [...prev, record]);
      setGradients(null);
      setGradientStats(null);
      setGradientJson("");
      toast.success("Gradient update submitted to the FL pipeline ✓");
    } catch (err) {
      toast.error(err.message || "Submission failed");
    } finally {
      setSubmitting(false);
      setTimeout(() => setPipelineStage(null), 1200);
    }
  }

  const lastSubmission = submissionHistory[submissionHistory.length - 1];

  return (
    <div className="space-y-4">
      {/* Status banner */}
      <div
        className={cn(
          "flex items-center gap-3 rounded-lg border px-4 py-3 text-xs",
          isActive ?
            "border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400"
          : "border-amber-500/30 bg-amber-500/5 text-amber-600 dark:text-amber-400",
        )}
      >
        <span
          className={cn(
            "h-2 w-2 shrink-0 rounded-full",
            isActive ? "bg-emerald-500 animate-pulse" : "bg-amber-500",
          )}
        />
        <span className="flex-1">
          {isActive ?
            <>
              Training{" "}
              <span className="font-semibold capitalize">{trainingStatus}</span>
              {" — "}
              Round{" "}
              <span className="mono-data font-bold">{currentRound ?? "—"}</span>
              . Submissions are queued for the next aggregation step.
            </>
          : <>
              Training is not running. The project lead must start training
              before you can submit gradient updates.
            </>
          }
        </span>
        {trainingStatus === "paused" && (
          <Badge
            variant="outline"
            className="border-amber-500/40 text-amber-600 dark:text-amber-400 text-[10px]"
          >
            Paused
          </Badge>
        )}
      </div>

      {/* Code editor + gradient JSON tabs */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <CardTitle className="text-sm">
              <Tabs value={editorTab} onValueChange={setEditorTab}>
                <TabsList className="h-7">
                  <TabsTrigger value="code" className="h-6 text-xs gap-1.5">
                    <FileCode2 size={11} />
                    Training Script
                  </TabsTrigger>
                  <TabsTrigger
                    value="gradients"
                    className="h-6 text-xs gap-1.5"
                  >
                    <ClipboardPaste size={11} />
                    Paste Gradients
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </CardTitle>

            {editorTab === "code" && (
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".py,.txt"
                  className="hidden"
                  onChange={handleFileUpload}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 text-xs"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload size={11} />
                  Upload .py
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 text-xs"
                  onClick={() => {
                    setCode(CODE_TEMPLATE);
                    toast.info("Template restored");
                  }}
                >
                  <RefreshCw size={11} />
                  Reset
                </Button>
              </div>
            )}

            {editorTab === "gradients" && (
              <div className="flex items-center gap-2">
                <input
                  ref={jsonInputRef}
                  type="file"
                  accept=".json,.txt"
                  className="hidden"
                  onChange={handleJsonUpload}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1.5 text-xs"
                  onClick={() => jsonInputRef.current?.click()}
                >
                  <Upload size={11} />
                  Upload JSON
                </Button>
              </div>
            )}
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {editorTab === "code" && (
            <LineNumberedEditor value={code} onChange={setCode} />
          )}

          {editorTab === "gradients" && (
            <div className="p-4 space-y-3">
              <p className="text-xs text-muted-foreground">
                Paste the JSON output from your local training script here (the{" "}
                <code className="bg-muted px-1 rounded text-[11px]">
                  print(json.dumps(gradients))
                </code>{" "}
                output).
              </p>
              <textarea
                value={gradientJson}
                onChange={(e) => setGradientJson(e.target.value)}
                spellCheck={false}
                placeholder={
                  '{\n  "conv1.weight": [0.002, -0.001, ...],\n  "fc1.bias": [0.0003, ...]\n}'
                }
                className={cn(
                  "h-56 w-full resize-none rounded-lg border border-border bg-[#0d1117]",
                  "p-4 font-mono text-[12px] leading-relaxed text-[#c9d1d9]",
                  "focus:outline-none focus:ring-1 focus:ring-primary/50",
                  "placeholder:text-[#6e7681]",
                )}
              />
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 w-full"
                onClick={handleParseJson}
                disabled={!gradientJson.trim()}
              >
                <ClipboardPaste size={13} />
                Parse & Validate Gradients
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Step 1 — Compute / validate gradients */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Step 1 — Generate Gradients</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Either run a local test to simulate gradients, or paste the JSON
                output from your real local training run in the "Paste
                Gradients" tab.
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleCompute}
              disabled={isComputing}
              className="gap-1.5 shrink-0"
            >
              {isComputing ?
                <RefreshCw size={13} className="animate-spin" />
              : <Play size={13} />}
              {isComputing ? "Computing…" : "Run Local Test"}
            </Button>
          </div>

          {gradients && gradientStats && (
            <GradientStats
              gradients={gradients}
              l2Norm={gradientStats.l2Norm}
              clippedNorm={gradientStats.clippedNorm}
              clipFactor={gradientStats.clipFactor}
            />
          )}
        </CardContent>
      </Card>

      {/* Step 2 — Submit to FL pipeline */}
      <Card className={cn(gradients && isActive && "border-primary/30")}>
        <CardContent className="p-4 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Step 2 — Submit to Pipeline</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Gradients are clipped (L2 norm) and masked (secure aggregation)
                on the server before entering aggregation. Your raw data never
                leaves your machine.
              </p>
            </div>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={submitting || !gradients || !isActive}
              className={cn(
                "gap-1.5 shrink-0",
                gradients && isActive ?
                  "bg-primary text-primary-foreground"
                : "",
              )}
            >
              {submitting ?
                <RefreshCw size={13} className="animate-spin" />
              : <Send size={13} />}
              {submitting ? "Submitting…" : "Submit to Model"}
            </Button>
          </div>

          {/* Pipeline visualization */}
          <PipelineVisualizer activeStage={pipelineStage} />
        </CardContent>
      </Card>

      {/* Last submission receipt */}
      {lastSubmission && (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2
                size={16}
                className="text-emerald-500 shrink-0 mt-0.5"
              />
              <div className="flex-1 space-y-1">
                <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                  Last Submission Accepted
                </p>
                <p className="text-xs text-muted-foreground">
                  {lastSubmission.message ||
                    "Gradient update accepted and queued for aggregation."}
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
                  <span className="text-[11px] text-muted-foreground">
                    Round{" "}
                    <span className="mono-data font-medium text-foreground">
                      {lastSubmission.round ?? "—"}
                    </span>
                  </span>
                  {lastSubmission.l2Norm != null && (
                    <span className="text-[11px] text-muted-foreground">
                      L2{" "}
                      <span className="mono-data font-medium text-foreground">
                        {Number(lastSubmission.l2Norm).toFixed(4)}
                      </span>
                    </span>
                  )}
                  {lastSubmission.clipFactor != null && (
                    <span className="text-[11px] text-muted-foreground">
                      Retained{" "}
                      <span className="mono-data font-medium text-foreground">
                        {(Number(lastSubmission.clipFactor) * 100).toFixed(1)}%
                      </span>
                    </span>
                  )}
                  <span className="text-[11px] text-muted-foreground">
                    at {lastSubmission.submittedAt}
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Submission history */}
      <SubmissionHistory history={submissionHistory} />

      {/* Privacy notice */}
      <div className="flex items-start gap-2 rounded-lg border border-border/50 bg-muted/10 px-3 py-2.5 text-[11px] text-muted-foreground">
        <AlertCircle size={12} className="shrink-0 mt-0.5 text-primary" />
        <span>
          <span className="font-semibold text-foreground">
            Privacy guaranteed.{" "}
          </span>
          Only gradient updates (not your training data or model code) are
          transmitted. The server applies L2 norm clipping and zero-sum masking
          before aggregating your update with other contributors. Trust scores
          and SABD results are server-internal and never returned to
          contributors.
        </span>
      </div>
    </div>
  );
}
