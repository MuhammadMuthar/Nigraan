"use client";
import { Workflow } from "lucide-react";
import type { TraceStep } from "@/lib/types";

/** Agent trace: every step the system ran, with timings and evidence. */
export function AgentTrace({ steps, title = "Agent trace" }: { steps: TraceStep[]; title?: string }) {
  const total = steps.reduce((s, x) => s + (x.ms || 0), 0);
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold"><Workflow className="size-4 text-accent" />{title}</div>
        <div className="tabular text-xs text-muted-foreground">{steps.length} steps · {total.toFixed(0)} ms</div>
      </div>
      <ol className="relative ml-2 border-l border-border">
        {steps.map((s, i) => (
          <li key={i} className="mb-3 ml-4">
            <span className="absolute -left-[5px] mt-1.5 size-2.5 rounded-full border-2 border-card bg-accent" />
            <div className="flex items-baseline justify-between gap-3">
              <div className="text-sm font-medium">{s.label}</div>
              <div className="tabular shrink-0 text-xs text-muted-foreground">{s.ms < 1 ? "<1" : s.ms.toFixed(0)} ms</div>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">{typeof s.detail === "string" ? s.detail : JSON.stringify(s.detail)}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
