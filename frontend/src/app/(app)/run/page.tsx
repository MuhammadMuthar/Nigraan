"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ArrowRight, CalendarPlus, CircleCheck, Download, Flag, Loader2, ShieldAlert } from "lucide-react";
import { api, getToken, API_URL } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { invalidateAll, useApi } from "@/lib/hooks";
import { dayFull, rs } from "@/lib/format";
import type { RunDetail } from "@/lib/types";
import { flaggedOpen, PageTitle } from "@/components/app/shell";
import { CashPanel } from "@/components/app/cash-panel";
import { DecisionBadge, FRAUD_NAMES } from "@/components/app/decision";
import { RulesComparisonSummary } from "@/components/app/rules-comparison";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CountUp, Empty, Skeleton, Stat } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/tooltip";

export default function RunPage() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useApi<{ run: RunDetail | null }>("/payment-runs/current");
  const [busy, setBusy] = useState<string | null>(null);
  const run = data?.run ?? null;
  const canApprove = user?.role === "approver" || user?.role === "owner";

  const greenPending = run ? run.lines.filter((l) => l.decision === "allow" && l.status === "pending") : [];

  async function approveGreen() {
    if (!run) return;
    setBusy("green");
    try {
      const r = await api.post<{ approved: number[]; skipped: { vendor: string; reason: string }[] }>(`/payment-runs/${run.id}/approve-green`);
      if (r.approved.length) toast.success(`Approved ${r.approved.length} green line(s).`);
      else if (!r.skipped.length) toast.message("No eligible green lines remain to approve.");
      if (r.skipped.length) toast.warning(`${r.skipped.length} line(s) still need approval: ${r.skipped.map((s) => `${s.vendor}: ${s.reason}`).join("; ")}`);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function exportCsv() {
    if (!run) return;
    setBusy("export");
    try {
      const res = await fetch(`${API_URL}/api/v1/payment-runs/${run.id}/export`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) throw new Error((await res.json()).message);
      const blob = await res.blob();
      const a = document.createElement("a");
      const url = URL.createObjectURL(blob);
      a.href = url;
      a.download = `nigraan_run_${run.id}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Demo CSV exported. Payments remain unsettled and included in the cash forecast.");
      invalidateAll();
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (loading && !data) {
    return <div className="grid gap-4"><Skeleton className="h-8 w-64" /><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-72" /><Skeleton className="h-64" /></div>;
  }
  if (error) return <Empty icon={<ShieldAlert />} title="Could not load the payment run"><p>{error.message}</p><Button variant="outline" className="mt-3" onClick={reload}>Retry</Button></Empty>;
  if (!run) {
    return (
      <>
        <PageTitle title="Payment run" sub="Before the owner releases payments, every line gets a verdict and the cash impact is shown." />
        <Empty icon={<CalendarPlus />} title="No payment run this week yet">
          Use <b>Load demo week</b> in the demo bar above to import this week&apos;s 40 vendor invoices. Nigraan scores every line and shows whether cash stays above the reserve.
        </Empty>
      </>
    );
  }

  return (
    <>
      <PageTitle
        title={run.name}
        sub={<>Payment date {dayFull(run.lines[0]?.pay_date)} · {run.lines.length} lines · {run.open_lines} awaiting a decision · scored by model <span className="font-mono text-xs">{run.model_version}</span></>}
      >
        <Tooltip content={canApprove ? "Approve every green line you are allowed to approve" : "Only an approver or the owner can release payments"}>
          <span>
            <Button variant="success" disabled={!canApprove || greenPending.length === 0 || !!busy} onClick={approveGreen}>
              {busy === "green" ? <Loader2 className="animate-spin" /> : <CircleCheck />}Approve all green ({greenPending.length} · {rs(greenPending.reduce((s, l) => s + l.amount, 0))})
            </Button>
          </span>
        </Tooltip>
        <Tooltip content={run.can_export ? "Download the demo CSV for approved lines. Account last four digits only; this does not settle payments." : "Every line needs a decision before the demo bank CSV can be exported"}>
          <span>
            <Button variant="outline" disabled={!run.can_export || !canApprove || !!busy} onClick={exportCsv}>
              {busy === "export" ? <Loader2 className="animate-spin" /> : <Download />}Export bank file
            </Button>
          </span>
        </Tooltip>
      </PageTitle>
      <p className="mb-5 text-xs text-muted-foreground">Demo bank export contains account last four digits only. It does not send money or confirm settlement; exported payments remain forecast obligations.</p>
      <p className="mb-5 text-xs text-muted-foreground">{run.approval_policy} The person who clears a blocked case cannot approve that payment.</p>

      <section aria-label="Payment run summary" className="stagger mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card><div className="p-5"><Stat label="Total payment lines" value={<CountUp value={run.lines.length} />} sub={`${rs(run.cash.run_total)} scheduled`} /></div></Card>
        <Link href="/flagged" className="lift group block rounded-lg">
          <Card className="h-full transition-colors group-hover:border-accent/40"><div className="p-5"><Stat label="Action required" value={<span className="inline-flex items-center gap-2"><CountUp value={flaggedOpen(run)} /><ArrowRight aria-hidden className="size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-accent" /></span>} sub={`${run.totals.blocked.count} payments blocked · ${run.totals.review.count} to review`} /></div></Card>
        </Link>
        <Card className="border-blocked/20"><div className="p-5"><Stat label="Blocked payment amount" value={<CountUp value={run.totals.blocked.amount} format={rs} />} sub="Resolve the cases before release" tone={run.totals.blocked.count ? "blocked" : undefined} /></div></Card>
        <Card><div className="p-5"><Stat label="13-week reserve outcome" value={run.cash.with_nigraan.stays_above_reserve ? "Above reserve" : "Reserve breach"} sub={run.cash.with_nigraan.first_breach ? `First breach ${dayFull(run.cash.with_nigraan.first_breach)}` : `Minimum cash ${rs(run.cash.with_nigraan.low_point)}`} tone={run.cash.with_nigraan.stays_above_reserve ? "allow" : "blocked"} /></div></Card>
      </section>
      <RulesComparisonSummary comparison={run.rules_comparison} />
      <CashPanel run={run} />
      <AttentionCard run={run} />
    </>
  );
}

function AttentionCard({ run }: { run: RunDetail }) {
  const flagged = run.lines
    .filter((l) => l.decision === "blocked" || l.decision === "review")
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const open = flaggedOpen(run);
  return (
    <Card className="mt-6 animate-rise-in overflow-hidden [animation-delay:200ms]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-base font-semibold"><Flag aria-hidden className="size-4 text-blocked" />Needs your attention</div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {open ? `${open} flagged line${open === 1 ? "" : "s"} awaiting a decision. Red lines stay locked until their case is resolved.` : "No flagged line is waiting on you."}
          </div>
        </div>
        <Button asChild><Link href="/flagged">Review flagged invoices<ArrowRight /></Link></Button>
      </div>
      {flagged.length === 0 ? (
        <div className="flex items-center gap-2 px-5 py-6 text-sm text-muted-foreground"><CircleCheck className="size-4 text-allow" />No payment line currently needs a risk review. Approval controls still apply.</div>
      ) : (
        <ul className="divide-y divide-border">
          {flagged.slice(0, 5).map((l, i) => (
            <li key={l.id} className="row-in" style={{ "--i": i } as React.CSSProperties}>
              <Link href={l.case ? `/cases/${l.case.id}` : "/flagged"} className="group flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 transition-colors hover:bg-muted/50">
                <DecisionBadge decision={l.decision} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">{l.vendor}<span className="ml-2 text-xs font-normal text-muted-foreground">{l.invoice_no}{l.fraud_type ? ` · ${FRAUD_NAMES[l.fraud_type]}` : ""}</span></span>
                  <span className="block truncate text-xs text-muted-foreground">{l.top_reason}</span>
                </span>
                <span className="tabular text-sm font-medium">{rs(l.amount)}</span>
                <ArrowRight aria-hidden className="size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-accent" />
              </Link>
            </li>
          ))}
          {flagged.length > 5 && (
            <li><Link href="/flagged" className="block px-5 py-3 text-center text-xs font-medium text-accent hover:underline">+ {flagged.length - 5} more flagged line{flagged.length - 5 === 1 ? "" : "s"}</Link></li>
          )}
        </ul>
      )}
    </Card>
  );
}
