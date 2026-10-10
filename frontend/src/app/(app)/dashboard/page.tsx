"use client";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, BadgeCheck, Brain, LayoutDashboard, ShieldAlert, ShieldCheck, Wallet } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { day, pct, rs, rsShort } from "@/lib/format";
import { PageTitle } from "@/components/app/shell";
import { FRAUD_NAMES } from "@/components/app/decision";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, Skeleton, Stat } from "@/components/ui/misc";
import { cn } from "@/lib/utils";

type M = { recall: number; precision_red: number; false_alarm_rate: number; pr_auc: number; rupees_protected_red?: number; rupees_fraud?: number };
type Summary = {
  company: { name: string; as_of: string; reserve: number; opening_cash: number; approval_limit: number };
  rupees_protected_this_month: number; open_cases: { count: number; amount: number };
  alerts_by_type: { type: string; name: string; count: number; amount: number; red: number }[];
  historical_confirmed: { type: string; name: string; count: number; amount: number }[];
  cash: { low_point: number; low_point_day: string; first_breach: string | null; reserve: number; stays_above_reserve: boolean; release_everything?: { first_breach: string | null; low_point: number } } | null;
  run: { total: number; by_decision: Record<string, number>; pending: number } | null;
  model_version: string;
  metrics: null | {
    test_period: string; generated_at: string;
    fraud: { n_payments: number; n_fraud: number; nigraan: M; baseline: M; per_type: Record<string, { name: string; n: number; caught: number; recall: number }> };
    late: { shipped: string; pr_auc: number; baseline_pr_auc: number; lr_pr_auc: number; xgb_pr_auc: number; precision_top20: number; brier: number; baseline_brier: number };
    cash: { mae: number; baseline_mae: number; improvement: number };
    robustness?: Record<string, { mean: number; min: number; max: number }>;
    extraction?: { field_accuracy: number; engine: string; files: number } | null;
  };
};

export default function Dashboard() {
  const { data, loading, error } = useApi<Summary>("/dashboard/summary");
  if (loading && !data) return <div className="grid gap-4"><Skeleton className="h-28" /><Skeleton className="h-80" /></div>;
  if (error || !data) return <Empty icon={<LayoutDashboard />} title="Dashboard unavailable">{error?.message}</Empty>;
  const m = data.metrics;
  const alerts = data.alerts_by_type.map((a) => ({ ...a, label: FRAUD_NAMES[a.type] ?? a.name, amountR: a.amount / 100 }));
  return (
    <>
      <PageTitle title="Dashboard" sub={`${data.company.name} · as of ${day(data.company.as_of, { weekday: "short", year: "numeric" })} · model ${data.model_version}`} />
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 text-xs">
        <span className="flex items-center gap-2 font-medium"><ShieldAlert aria-hidden className="size-4 text-muted-foreground" />Synthetic demo · fictional company · no real-world performance claim</span>
        <span className="text-muted-foreground">Reporting month: {day(data.company.as_of, { day: undefined, month: "long", year: "numeric" })}</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="border-[#0B1422] bg-[#0B1422] text-white [&_.text-muted-foreground]:text-slate-300"><CardContent className="pt-5"><ShieldCheck aria-hidden className="mb-4 size-5 text-teal-300" /><Stat label="Rupees protected this month" value={rs(data.rupees_protected_this_month)} sub="blocked by Nigraan or rejected as fraud" /></CardContent></Card>
        <Card><CardContent className="pt-5"><ShieldAlert aria-hidden className="mb-4 size-5 text-muted-foreground" /><Stat label="Open cases" value={data.open_cases.count} sub={`${rs(data.open_cases.amount)} on hold`} tone={data.open_cases.count ? "blocked" : undefined} />
          <Link href="/cases" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">Review cases<ArrowRight className="size-3" /></Link></CardContent></Card>
        <Card><CardContent className="pt-5"><Wallet aria-hidden className="mb-4 size-5 text-muted-foreground" />{data.cash ? <Stat label="Cash low point (13 weeks)" value={rs(data.cash.low_point)} sub={data.cash.first_breach ? `breaches reserve ${day(data.cash.first_breach)}` : `${day(data.cash.low_point_day)} · above the ${rs(data.cash.reserve)} reserve`} tone={data.cash.first_breach ? "blocked" : "allow"} /> : <Stat label="Cash low point (13 weeks)" value="—" sub="Cash projection unavailable" />}
          <Link href="/cash" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">Explore cash outlook<ArrowRight className="size-3" /></Link>
          {data.cash?.release_everything?.first_breach && <div className="mt-1 text-[11px] text-blocked">Without the firewall: breach on {day(data.cash.release_everything.first_breach, { weekday: "short" })}</div>}</CardContent></Card>
        <Card><CardContent className="pt-5"><LayoutDashboard aria-hidden className="mb-4 size-5 text-muted-foreground" />{data.run ? <Stat label="This week's run" value={`${data.run.total} lines`} sub={<span><span className="text-allow">{data.run.by_decision.allow} allow</span> · <span className="text-review">{data.run.by_decision.review} review</span> · <span className="text-blocked">{data.run.by_decision.blocked} blocked</span> · {data.run.pending} awaiting</span>} /> : <Stat label="This week's run" value="—" sub="load the demo week" />}<Link href="/run" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">Open payment run<ArrowRight className="size-3" /></Link></CardContent></Card>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Alerts this month by fraud pattern</CardTitle><CardDescription>Review and blocked lines in this demo’s payment runs, by the engine&apos;s suspected pattern</CardDescription></CardHeader>
          <CardContent>
            {alerts.length === 0 ? <div className="py-10 text-center text-sm text-muted-foreground">No alerts in the current demo yet. Load the demo week to see risk patterns.</div> : (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={alerts} layout="vertical" margin={{ left: 0, right: 16, bottom: 12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => rsShort(v * 100)} tick={{ fontSize: 11 }} label={{ value: "Amount (Rs)", position: "insideBottom", offset: -10, fontSize: 11 }} />
                  <YAxis type="category" dataKey="label" width={130} tick={{ fontSize: 11 }} />
                  <RTooltip formatter={(v) => rs(Number(v) * 100)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  <Bar dataKey="amountR" name="Amount" fill="var(--blocked)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
            {alerts.length > 0 && <div className="mt-3 grid gap-2 text-xs">{alerts.map((a) => <div key={a.type} className="flex flex-wrap justify-between gap-1 border-t border-border pt-2"><span className="font-medium">{a.label}</span><span className="text-muted-foreground">{a.count} alerts · {a.red} blocked · {rs(a.amount)}</span></div>)}</div>}
            <div className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
              Training history (internal audit, months 1-10): {data.historical_confirmed.map((h) => `${FRAUD_NAMES[h.type] ?? h.type} ${h.count}`).join(" · ")}
            </div>
          </CardContent>
        </Card>

        {m ? (
          <Card>
            <CardHeader>
              <Badge variant="outline" className="mb-2 w-fit">Offline ML evaluation · synthetic hold-out</Badge>
              <CardTitle className="flex items-center gap-1.5"><BadgeCheck className="size-4 text-accent" />Fraud firewall vs rules-only baseline</CardTitle>
              <CardDescription>Held-out test: {m.test_period}. {m.fraud.n_payments} payments, {m.fraud.n_fraud} planted frauds the models never saw.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-[1fr_90px_90px] gap-y-2 text-sm">
                <div className="text-xs text-muted-foreground" /><div className="text-right text-xs font-semibold text-accent">Nigraan</div><div className="text-right text-xs font-semibold text-muted-foreground">Rules only</div>
                {([["Fraud caught (recall)", "recall", true], ["Precision at red", "precision_red", true], ["False-alarm rate", "false_alarm_rate", false], ["PR-AUC", "pr_auc", true]] as const).map(([label, key, higher]) => (
                  <Row key={key} label={label} a={m.fraud.nigraan[key]} b={m.fraud.baseline[key]} higher={higher} fmt={key === "pr_auc" ? (x) => x.toFixed(2) : (x) => pct(x, 1)} />
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {Object.entries(m.fraud.per_type).map(([t, v]) => (
                  <Badge key={t} variant="outline">{FRAUD_NAMES[t]} {v.caught}/{v.n}</Badge>
                ))}
              </div>
              {m.robustness && (
                <div className="mt-4 rounded-md bg-muted px-3 py-2 text-xs">
                  <b>Across 5 different synthetic companies:</b> recall {pct(m.robustness.recall.mean)} (range {pct(m.robustness.recall.min)}-{pct(m.robustness.recall.max)}), false alarms {pct(m.robustness.false_alarm_rate.mean, 1)}, vs rules-only recall {pct(m.robustness.baseline_recall.mean)}.
                </div>
              )}
              <div className="mt-2 text-xs text-muted-foreground">Rupees caught at red in the test months: {rs(m.fraud.nigraan.rupees_protected_red ?? 0)} of {rs(m.fraud.nigraan.rupees_fraud ?? 0)}.</div>
            </CardContent>
          </Card>
        ) : <Card><CardContent className="pt-5 text-sm text-muted-foreground">No evaluation results yet.</CardContent></Card>}
      </div>

      {m && (
        <div className="mt-5 grid gap-5 lg:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><Wallet className="size-4 text-accent" />Late-payment model</CardTitle><CardDescription>Receivables issued in the test months, predicted at issue date</CardDescription></CardHeader>
            <CardContent className="grid gap-2 text-sm">
              <div className="grid grid-cols-[1fr_auto] gap-y-1.5">
                <span>Shipped model</span><b className="uppercase">{m.late.shipped}</b>
                <span>PR-AUC</span><b className="tabular">{m.late.pr_auc?.toFixed(2)}</b>
                <span className="text-muted-foreground">vs late-rate baseline</span><span className="tabular text-muted-foreground">{m.late.baseline_pr_auc.toFixed(2)}</span>
                <span className="text-muted-foreground">vs logistic regression / XGBoost</span><span className="tabular text-muted-foreground">{m.late.lr_pr_auc.toFixed(2)} / {m.late.xgb_pr_auc.toFixed(2)}</span>
                <span>Precision in top 20% riskiest</span><b className="tabular">{pct(m.late.precision_top20)}</b>
                <span>Brier score (lower is better)</span><b className="tabular">{m.late.brier?.toFixed(3)} <span className="font-normal text-muted-foreground">vs {m.late.baseline_brier.toFixed(3)}</span></b>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><ShieldCheck className="size-4 text-accent" />Cash forecast accuracy</CardTitle><CardDescription>Weekly receipts, rolling backtest over the test months</CardDescription></CardHeader>
            <CardContent>
              <div className="tabular text-3xl font-semibold text-accent">{pct(m.cash.improvement)}</div>
              <div className="text-sm">lower weekly error than assuming everyone pays on the due date</div>
              <div className="mt-2 text-xs text-muted-foreground">Mean absolute error {rs(Math.round(m.cash.mae) * 100)}/week vs {rs(Math.round(m.cash.baseline_mae) * 100)}/week</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-1.5"><Brain className="size-4 text-accent" />Document reader</CardTitle><CardDescription>Field accuracy on the evaluated demo-week PDFs</CardDescription></CardHeader>
            <CardContent>
              {m.extraction ? (<><div className="tabular text-3xl font-semibold text-accent">{pct(m.extraction.field_accuracy, 1)}</div><div className="text-sm">of fields extracted exactly ({m.extraction.engine}, {m.extraction.files} files)</div></>) : <div className="text-sm text-muted-foreground">Run <span className="font-mono">python -m ml.eval_extraction</span></div>}
              <div className="mt-2 text-xs text-muted-foreground">The regex fallback was written for these three invoice layouts, so this proves the pipeline, not accuracy on unseen layouts (that is Gemini&apos;s job). Low-confidence fields are highlighted; the LLM never sets a score or a cash number.</div>
            </CardContent>
          </Card>
        </div>
      )}
      <div className="mt-5 flex items-center gap-2 text-xs text-muted-foreground"><ShieldAlert className="size-3.5" />All data is synthetic (seeded generator, fictional company). These numbers prove the pipeline, not real-world accuracy; a pilot is the next step.</div>
    </>
  );
}

function Row({ label, a, b, higher, fmt }: { label: string; a: number; b: number; higher: boolean; fmt: (x: number) => string }) {
  const better = higher ? a >= b : a <= b;
  return (
    <>
      <div>{label}</div>
      <div className={cn("tabular text-right font-semibold", better ? "text-foreground" : "text-review")}>{fmt(a)}</div>
      <div className="tabular text-right text-muted-foreground">{fmt(b)}</div>
    </>
  );
}
