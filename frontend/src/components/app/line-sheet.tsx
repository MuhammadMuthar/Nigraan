"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { rs } from "@/lib/format";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DecisionBadge, ENGINE_LABEL, FRAUD_NAMES, ScoreGauge } from "@/components/app/decision";
import { AgentTrace } from "@/components/app/trace";
import { EngineBars } from "@/components/app/engine-bars";
import type { Reason, TraceStep } from "@/lib/types";

export type ScoreDetail = {
  payment_id: number; vendor: string; invoice_no: string; amount: number; score: number; decision: string; reasons: Reason[];
  engines: { signals: Record<string, number>; contributions: Record<string, number>; fraud_type: string | null };
  evidence: Record<string, unknown>; trace: TraceStep[]; model_version: string; scored_at: string; case_id: number | null;
  invoice_source: string; extraction: { engine?: string } | null;
};

export function LineSheet({ paymentId, onClose }: { paymentId: number | null; onClose: () => void }) {
  const [res, setRes] = useState<ScoreDetail | null>(null);
  useEffect(() => {
    if (paymentId) api.get<ScoreDetail>(`/payments/${paymentId}/score`).then(setRes).catch(() => setRes(null));
  }, [paymentId]);
  const d = res && res.payment_id === paymentId ? res : null;
  return (
    <Sheet open={paymentId !== null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent>
        <div className="border-b border-border p-5 pr-12">
          <SheetTitle>{d ? d.vendor : "Loading…"}</SheetTitle>
          <SheetDescription>{d ? `Invoice ${d.invoice_no} · ${rs(d.amount)} · source: ${d.invoice_source}` : " "}</SheetDescription>
        </div>
        {!d ? (
          <div className="flex items-center gap-2 p-5 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Fetching score, evidence and trace…</div>
        ) : (
          <div className="grid gap-6 p-5">
            <div className="flex items-center gap-5">
              <ScoreGauge score={d.score} decision={d.decision} />
              <div className="grid gap-1.5">
                <DecisionBadge decision={d.decision} large />
                {d.engines.fraud_type && <div className="text-xs text-muted-foreground">Suspected: <b>{FRAUD_NAMES[d.engines.fraud_type]}</b></div>}
                <div className="text-[11px] text-muted-foreground">model {d.model_version}</div>
              </div>
              {d.case_id && (
                <Button asChild size="sm" className="ml-auto"><Link href={`/cases/${d.case_id}`}>Open case<ArrowRight /></Link></Button>
              )}
            </div>
            <div>
              <div className="mb-2 text-sm font-semibold">Why</div>
              <ul className="grid gap-1.5">
                {d.reasons.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <Badge variant={r.engine === "info" ? "outline" : "accent"} className="mt-0.5 shrink-0">{ENGINE_LABEL[r.engine] ?? r.engine}</Badge>
                    <span className={r.weak ? "text-muted-foreground" : ""}>{r.text}</span>
                  </li>
                ))}
                {d.reasons.length === 0 && <li className="text-sm text-muted-foreground">No risk signals.</li>}
              </ul>
            </div>
            <EngineBars contributions={d.engines.contributions} signals={d.engines.signals} />
            <AgentTrace steps={d.trace} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
