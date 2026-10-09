"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarPlus, CircleCheck, Download, Eye, Loader2, Lock, PauseCircle, ShieldAlert, UserCheck } from "lucide-react";
import { api, getToken, API_URL } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { dateTime, dayFull, rs } from "@/lib/format";
import type { RunDetail, RunLine } from "@/lib/types";
import { PageTitle } from "@/components/app/shell";
import { CashPanel } from "@/components/app/cash-panel";
import { DecisionBadge, ENGINE_LABEL, FRAUD_NAMES, ScoreBar } from "@/components/app/decision";
import { LineSheet } from "@/components/app/line-sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Empty, Skeleton } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Filter = "all" | "blocked" | "review" | "allow";

const STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting approval", approved: "Approved", blocked: "Locked", held: "Held", rejected: "Rejected (fraud)", released: "Released",
};

export default function RunPage() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useApi<{ run: RunDetail | null }>("/payment-runs/current");
  const [filter, setFilter] = useState<Filter>("all");
  const [sheet, setSheet] = useState<number | null>(null);
  const [review, setReview] = useState<RunLine | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const run = data?.run ?? null;
  const canApprove = user?.role === "approver" || user?.role === "owner";

  const lines = useMemo(() => (run ? run.lines.filter((l) => filter === "all" || l.decision === filter) : []), [run, filter]);
  const greenPending = run ? run.lines.filter((l) => l.decision === "allow" && l.status === "pending") : [];

  async function approveGreen() {
    if (!run) return;
    setBusy("green");
    try {
      const r = await api.post<{ approved: number[]; skipped: { vendor: string; reason: string }[] }>(`/payment-runs/${run.id}/approve-green`);
      toast.success(`Approved ${r.approved.length} green line(s).`);
      if (r.skipped.length) toast.warning(`${r.skipped.length} green line(s) are above the approval limit and need the owner: ${r.skipped.map((s) => s.vendor).join(", ")}`);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function act(kind: "approve" | "hold", ids: number[], note?: string) {
    if (!run) return;
    setBusy(kind + ids.join(","));
    try {
      await api.post(`/payment-runs/${run.id}/${kind}`, { payment_ids: ids, note });
      toast.success(kind === "approve" ? "Released for payment." : "Line held.");
      setReview(null);
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
      a.href = URL.createObjectURL(blob);
      a.download = `nigraan_run_${run.id}.csv`;
      a.click();
      toast.success("Bank file exported. Approved lines are now released.");
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (loading && !data) {
    return <div className="grid gap-4"><Skeleton className="h-8 w-64" /><Skeleton className="h-72" /><Skeleton className="h-96" /></div>;
  }
  if (error) return <Empty icon={<ShieldAlert />} title="Could not load the payment run">{error.message}</Empty>;
  if (!run) {
    return (
      <>
        <PageTitle title="Payment run" sub="Before the owner releases payments, every line gets a verdict and the cash impact is shown." />
        <Empty icon={<CalendarPlus />} title="No payment run this week yet">
          Use <b>Load demo week</b> in the demo bar above to import this week&apos;s 40 vendor invoices. Nigraan scores every line in about a second and shows whether cash stays above the reserve.
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
        <Tooltip content={run.can_export ? "Download the bank upload file (approved lines only)" : "Every line needs a decision before the bank file can be exported"}>
          <span>
            <Button variant="outline" disabled={!run.can_export || !canApprove || !!busy} onClick={exportCsv}>
              {busy === "export" ? <Loader2 className="animate-spin" /> : <Download />}Export bank file
            </Button>
          </span>
        </Tooltip>
      </PageTitle>

      <CashPanel run={run} />

      <Card className="mt-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
            <TabsList>
              <TabsTrigger value="all">All {run.lines.length}</TabsTrigger>
              <TabsTrigger value="blocked"><span className="size-2 rounded-full bg-blocked" />Blocked {run.totals.blocked.count}</TabsTrigger>
              <TabsTrigger value="review"><span className="size-2 rounded-full bg-review" />Review {run.totals.review.count}</TabsTrigger>
              <TabsTrigger value="allow"><span className="size-2 rounded-full bg-allow" />Allow {run.totals.allow.count}</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="text-xs text-muted-foreground">Click a line to see the evidence and the agent trace</div>
        </div>
        <Table>
          <THead>
            <TR>
              <TH>Verdict</TH><TH>Score</TH><TH>Payee</TH><TH className="text-right">Amount</TH><TH>Top reason</TH><TH>Entered by</TH><TH>Status</TH><TH className="text-right">Action</TH>
            </TR>
          </THead>
          <TBody>
            {lines.map((l) => (
              <TR key={l.id} className={cn("cursor-pointer hover:bg-muted/50", l.decision === "blocked" && "bg-blocked-soft/30")} onClick={() => setSheet(l.id)}>
                <TD><DecisionBadge decision={l.decision} />{l.override && <div className="mt-1 text-[10px] text-review">overridden after case</div>}</TD>
                <TD><ScoreBar score={l.score} /></TD>
                <TD>
                  <div className="font-medium">{l.vendor}</div>
                  <div className="text-xs text-muted-foreground">{l.invoice_no} · {l.bank_name} ••{l.bank_last4}{l.fraud_type && l.decision !== "allow" ? ` · ${FRAUD_NAMES[l.fraud_type]}` : ""}</div>
                </TD>
                <TD className="tabular whitespace-nowrap text-right font-medium">{rs(l.amount)}</TD>
                <TD className="max-w-[360px]">
                  <div className={cn("line-clamp-2 text-sm", l.decision === "allow" && "text-muted-foreground")}>{l.top_reason}</div>
                  {l.info.length > 0 && <div className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">{l.info[0]}</div>}
                </TD>
                <TD className="text-xs"><div>{l.created_by}</div><div className="text-muted-foreground">{dateTime(l.created_at)}</div></TD>
                <TD className="text-xs">
                  <span className={cn(l.status === "approved" && "text-allow", l.status === "blocked" && "text-blocked", l.status === "held" && "text-review")}>{STATUS_LABEL[l.status] ?? l.status}</span>
                  {l.approved_by && <div className="text-muted-foreground">by {l.approved_by}</div>}
                </TD>
                <TD className="text-right" onClick={(e) => e.stopPropagation()}>
                  <LineAction line={l} canApprove={canApprove} busy={busy} onApprove={() => act("approve", [l.id])} onReview={() => setReview(l)} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>

      <ReviewDialog line={review} userId={user?.id} canApprove={canApprove} busy={!!busy}
        onClose={() => setReview(null)} onApprove={(note) => review && act("approve", [review.id], note)} onHold={(note) => review && act("hold", [review.id], note)} />
      <LineSheet paymentId={sheet} onClose={() => setSheet(null)} />
    </>
  );
}

function LineAction({ line: l, canApprove, busy, onApprove, onReview }: {
  line: RunLine; canApprove: boolean; busy: string | null; onApprove: () => void; onReview: () => void;
}) {
  if (l.decision === "blocked" && l.status === "blocked") {
    return (
      <div className="flex items-center justify-end gap-1.5">
        <Tooltip content="Blocked by Nigraan: this line cannot be released. Resolve the case first.">
          <span><Button size="sm" variant="outline" disabled aria-label="Release disabled"><Lock />Release</Button></span>
        </Tooltip>
        {l.case && <Button asChild size="sm" variant="danger"><Link href={`/cases/${l.case.id}`}><Eye />View case</Link></Button>}
      </div>
    );
  }
  if (l.status !== "pending") {
    return l.case ? <Button asChild size="sm" variant="ghost"><Link href={`/cases/${l.case.id}`}>Case</Link></Button> : null;
  }
  if (l.decision === "review") {
    return <Button size="sm" variant="outline" className="border-review/40 text-review hover:bg-review-soft" onClick={onReview}><UserCheck />Second approval</Button>;
  }
  return (
    <Tooltip content={canApprove ? "Approve this line" : "Approver or owner role needed"}>
      <span><Button size="sm" variant="outline" disabled={!canApprove || !!busy} onClick={onApprove}><CircleCheck />Approve</Button></span>
    </Tooltip>
  );
}

function ReviewDialog({ line, userId, canApprove, busy, onClose, onApprove, onHold }: {
  line: RunLine | null; userId?: number; canApprove: boolean; busy: boolean; onClose: () => void; onApprove: (note: string) => void; onHold: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const own = line && line.created_by_id === userId;
  return (
    <Dialog open={!!line} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        {line && (
          <>
            <DialogTitle>Second approval: {line.vendor}</DialogTitle>
            <DialogDescription>{rs(line.amount)} · invoice {line.invoice_no} · entered by {line.created_by}. Yellow lines need a second person who did not enter them.</DialogDescription>
            <div className="mt-4 grid gap-1.5">
              {line.reasons.map((r, i) => (
                <div key={i} className="flex gap-2 text-sm"><Badge variant="review" className="mt-0.5 shrink-0">{ENGINE_LABEL[r.engine] ?? r.engine}</Badge>{r.text}</div>
              ))}
              {line.info.map((t, i) => <div key={`i${i}`} className="text-xs text-muted-foreground">{t}</div>)}
            </div>
            {own && <div className="mt-4 rounded-md bg-review-soft px-3 py-2 text-sm text-review">You entered this line, so you cannot approve it. Ask another approver or the owner.</div>}
            {!canApprove && <div className="mt-4 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">Only an approver or the owner can release payments.</div>}
            <Textarea className="mt-4" placeholder="Note (e.g. called vendor on registered number, confirmed new account)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" disabled={busy || !canApprove} onClick={() => onHold(note)}><PauseCircle />Hold</Button>
              <Button variant="success" disabled={busy || !!own || !canApprove} onClick={() => onApprove(note)}><UserCheck />Approve as second approver</Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
