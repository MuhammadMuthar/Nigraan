import { Ban, CircleCheck, Lock, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { CountUp } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import type { Decision } from "@/lib/types";

const META: Record<string, { label: string; variant: "allow" | "review" | "blocked" | "default"; Icon: typeof Ban }> = {
  allow: { label: "Allow", variant: "allow", Icon: CircleCheck },
  review: { label: "Review", variant: "review", Icon: TriangleAlert },
  blocked: { label: "Blocked", variant: "blocked", Icon: Ban },
  unscored: { label: "Unscored", variant: "default", Icon: Lock },
};

/** Traffic light = colour + icon + word (never colour alone). */
export function DecisionBadge({ decision, className, large }: { decision: Decision | string; className?: string; large?: boolean }) {
  const m = META[decision] ?? META.unscored;
  return (
    <Badge variant={m.variant} className={cn(large && "px-3 py-1 text-sm", className)}>
      <m.Icon className={large ? "size-4" : "size-3.5"} aria-hidden />
      {m.label}
    </Badge>
  );
}

export function ScoreBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-muted-foreground">—</span>;
  const color = score >= 75 ? "bg-blocked" : score >= 40 ? "bg-review" : "bg-allow";
  return (
    <div className="flex items-center gap-2" aria-label={`Risk score ${score} of 100`}>
      <span className="tabular w-7 text-right text-sm font-semibold">{score}</span>
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        <div className={cn("grow-x h-full rounded-full", color)} style={{ width: `${Math.max(3, score)}%` }} />
      </div>
    </div>
  );
}

export function ScoreGauge({ score, decision }: { score: number; decision: string }) {
  const r = 46;
  const c = Math.PI * r;
  const color = decision === "blocked" ? "var(--blocked)" : decision === "review" ? "var(--review)" : "var(--allow)";
  return (
    <div className="relative h-[74px] w-[120px]">
      <svg viewBox="0 0 120 70" className="h-full w-full" aria-label={`Risk score ${score}`}>
        <path d="M 14 62 A 46 46 0 0 1 106 62" fill="none" stroke="var(--muted)" strokeWidth="10" strokeLinecap="round" />
        <path d="M 14 62 A 46 46 0 0 1 106 62" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" className="gauge-arc"
          style={{ strokeDasharray: `${(c * score) / 100} ${c}` }} />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="tabular text-2xl font-bold leading-none"><CountUp value={score} duration={1100} /></div>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">risk / 100</div>
      </div>
    </div>
  );
}

export const FRAUD_NAMES: Record<string, string> = {
  F1: "Duplicate invoice", F2: "Bank-detail change", F3: "Shell vendor", F4: "Inflated price",
  F5: "Split payment", F7: "Out-of-hours payment", ANOMALY: "Unusual payment",
};

export const ENGINE_LABEL: Record<string, string> = {
  rules: "Policy rules", duplicate: "Duplicate detector (ML)", graph: "Relationship graph (rules)", risk_model: "Risk model (XGBoost)",
  anomaly: "Anomaly detector (ML)", info: "Note",
};
