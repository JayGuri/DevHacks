import { useState } from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const ATTACKS = [
  { value: "sign_flipping", label: "Sign Flipping", desc: "Flip gradient signs — collapses FedAvg" },
  { value: "scaling", label: "Scaling", desc: "Multiply gradients ×50 — dominates aggregation" },
  { value: "random_noise", label: "Random Noise", desc: "Replace with random noise ×10" },
  { value: "zero_gradient", label: "Zero Gradient", desc: "Send all zeros — free rider" },
  { value: "gaussian_noise", label: "Gaussian Noise", desc: "Add large Gaussian noise to update" },
];

const AGGREGATORS = [
  { value: "trimmed_mean", label: "Trimmed Mean", desc: "Drop top/bottom k gradients" },
  { value: "coordinate_median", label: "Coordinate Median", desc: "Per-coordinate median" },
  { value: "krum", label: "Krum", desc: "Select closest gradient to centroid" },
  { value: "bulyan", label: "Bulyan", desc: "Krum + trimmed mean combo" },
  { value: "reputation", label: "Reputation", desc: "SABD trust-weighted average" },
];

const ALPHA_OPTIONS = [
  { value: 0.1, label: "0.1 — Extreme Non-IID" },
  { value: 0.5, label: "0.5 — Moderate ★" },
  { value: 10.0, label: "10.0 — Near-IID" },
];

const ROUND_OPTIONS = [50, 100, 150];

export default function NewProjectDialog({ open, onOpenChange, onSubmit }) {
  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm({
    defaultValues: {
      name: "", description: "", visibility: "public", numClients: 10,
      byzantineFraction: 0.2, attackType: "sign_flipping",
      aggregationMethod: "trimmed_mean", dirichletAlpha: 0.5, numRounds: 50,
      useDifferentialPrivacy: true, dpNoiseMultiplier: 0.1, sabdAlpha: 0.5,
    },
  });

  const vals = watch();
  const numByz = Math.floor(vals.numClients * vals.byzantineFraction);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display">New Project</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1fr_240px]">
            {/* Left: form */}
            <div className="space-y-4">
              <div>
                <Label>Name *</Label>
                <Input {...register("name", { required: "Required" })} placeholder="My FL Experiment" />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div>
                <Label>Description</Label>
                <Input {...register("description")} placeholder="Optional description" />
              </div>
              <div>
                <Label>Visibility</Label>
                <Select value={vals.visibility} onValueChange={(v) => setValue("visibility", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="public">Public — anyone can request to join</SelectItem>
                    <SelectItem value="private">Private — invite code required</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Clients: {vals.numClients}</Label>
                <Slider min={2} max={20} step={1} value={[vals.numClients]} onValueChange={([v]) => setValue("numClients", v)} />
              </div>
              <div>
                <Label>Byzantine Fraction: {vals.byzantineFraction.toFixed(2)} ({numByz} adversarial)</Label>
                <Slider min={0} max={0.5} step={0.05} value={[vals.byzantineFraction]} onValueChange={([v]) => setValue("byzantineFraction", v)} />
              </div>
              <div>
                <Label>Attack Type</Label>
                <Select value={vals.attackType} onValueChange={(v) => setValue("attackType", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ATTACKS.map((a) => (<SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">{ATTACKS.find((a) => a.value === vals.attackType)?.desc}</p>
              </div>
              <div>
                <Label>Aggregation Method</Label>
                <Select value={vals.aggregationMethod} onValueChange={(v) => setValue("aggregationMethod", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {AGGREGATORS.map((a) => (<SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">{AGGREGATORS.find((a) => a.value === vals.aggregationMethod)?.desc}</p>
              </div>
              <div>
                <Label>Dirichlet α</Label>
                <div className="flex gap-2">
                  {ALPHA_OPTIONS.map((o) => (
                    <button key={o.value} type="button" onClick={() => setValue("dirichletAlpha", o.value)}
                      className={cn("rounded-md border px-2 py-1 text-xs", vals.dirichletAlpha === o.value ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground")}>{o.label}</button>
                  ))}
                </div>
              </div>
              <div>
                <Label>Rounds</Label>
                <div className="flex gap-2">
                  {ROUND_OPTIONS.map((r) => (
                    <button key={r} type="button" onClick={() => setValue("numRounds", r)}
                      className={cn("rounded-md border px-3 py-1 text-xs mono-data", vals.numRounds === r ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground")}>{r}</button>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={vals.useDifferentialPrivacy} onCheckedChange={(v) => setValue("useDifferentialPrivacy", v)} />
                <Label>Differential Privacy</Label>
              </div>
              {vals.useDifferentialPrivacy && (
                <div>
                  <Label>Noise Multiplier: {vals.dpNoiseMultiplier.toFixed(2)}</Label>
                  <Slider min={0.01} max={1} step={0.01} value={[vals.dpNoiseMultiplier]} onValueChange={([v]) => setValue("dpNoiseMultiplier", v)} />
                </div>
              )}
              <div>
                <Label>SABD Alpha: {vals.sabdAlpha.toFixed(1)}</Label>
                <Slider min={0} max={1} step={0.1} value={[vals.sabdAlpha]} onValueChange={([v]) => setValue("sabdAlpha", v)} />
                <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
                  <span>0 Legacy</span><span>0.5 Recommended ★</span><span>1.0 Full</span>
                </div>
              </div>
            </div>

            {/* Right: preview */}
            <Card className="h-fit">
              <CardContent className="space-y-2 p-3 text-xs">
                <p className="metric-label text-muted-foreground">Preview</p>
                <p>{vals.visibility === "private" ? "🔒 Private" : "🌐 Public"}</p>
                <p>{vals.numClients} clients · {numByz} adversarial</p>
                <p>{vals.attackType.replace(/_/g, " ")}</p>
                <p>{vals.aggregationMethod.replace(/_/g, " ")}</p>
                <p>DP: {vals.useDifferentialPrivacy ? "ON" : "OFF"}</p>
                <p>{vals.numRounds} rounds · α={vals.dirichletAlpha}</p>
                <Badge variant="outline" className="mono-data">SABD {vals.sabdAlpha.toFixed(1)}</Badge>
              </CardContent>
            </Card>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit">Create Project</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
