"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, CalendarPlus, CircleCheck, Eye, Flag, Loader2, Lock, PauseCircle, Search, ShieldAlert, UserCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { dateTime, dayFull, rs } from "@/lib/format";
import type { RunDetail, RunLine } from "@/lib/types";
import { flaggedOpen, PageTitle } from "@/components/app/shell";
import { DecisionBadge, ENGINE_LABEL, FRAUD_NAMES, ScoreBar } from "@/components/app/decision";
import { LineSheet } from "@/components/app/line-sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { CountUp, Empty, Skeleton, Stat } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Filter = "flagged" | "blocked" | "review" | "allow" | "all";
const FILTERS: Filter[] = ["flagged", "blocked", "review", "allow", "all"];

const STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting approval", approved: "Approved", blocked: "Locked", held: "Held", rejected: "Rejected (fraud)", released: "Settled", exported: "Exported · unsettled",
};

function matches(l: RunLine, f: Filter) {
  if (f === "all") return true;
  if (f === "flagged") return l.decision === "blocked" || l.decision === "review";
  return l.decision === f;
}

export default function FlaggedPage() {
  return <Suspense fallback={<Loading />}><FlaggedInvoices /></Suspense>;
}

function Loading() {
  return <div className="grid gap-4"><Skeleton className="h-8 w-64" /><div className="grid gap-3 sm:grid-cols-3"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-96" /></div>;
}

function FlaggedInvoices() {
  const { user } = useAuth();
  const params = useSearchParams();
  const initial = params.get("view") as Filter | null;
  const { data, loading, error, reload } = useApi<{ run: RunDetail | null }>("/payment-runs/current");
  const [filter, setFilter] = useState<Filter>(initial && FILTERS.includes(initial) ? initial : "flagged");
  const [query, setQuery] = useState("");
  const [sheet, setSheet] = useState<number | null>(null);
  const [review, setReview] = useState<RunLine | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const run = data?.run ?? null;
  const canApprove = user?.role === "approver" || user?.role === "owner";

  const lines = useMemo(() => {
    if (!run) return [];
    const q = query.trim().toLowerCase();
    return run.lines.filter((l) => matches(l, filter) && (!q || `${l.vendor} ${l.invoice_no} ${l.top_reason ?? ""}`.toLowerCase().includes(q)));
  }, [run, filter, query]);
  const count = (f: Filter) => (run ? run.lines.filter((l) => matches(l, f)).length : 0);

  async function act(kind: "approve" | "hold", ids: number[], note?: string) {
    if (!run) return;
    setBusy(kind + ids.join(","));
    try {
      await api.post(`/payment-runs/${run.id}/${kind}`, { payment_ids: ids, note });
      toast.success(kind === "approve" ? "Approved for payment." : "Line held.");
      setReview(null);
      await reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (loading && !data) return <Loading />;
  if (error) return <Empty icon={<ShieldAlert />} title="Could not load the flagged invoices"><p>{error.message}</p><Button variant="outline" className="mt-3" onClick={reload}>Retry</Button></Empty>;
  if (!run) {
    return (
      <>
        <PageTitle title="Flagged invoices" sub="Every payment line Nigraan blocked or sent for a second approval, with the evidence behind each verdict." />
        <Empty icon={<CalendarPlus />} title="No payment run this week yet">
          Use <b>Load demo week</b> in the demo bar above. Nigraan scores all 40 invoices in about a second and lists the risky ones here.
        </Empty>
      </>
    );
  }

  const open = flaggedOpen(run);
  return (
    <>
      <PageTitle
        title="Flagged invoices"
        sub={<>{run.name} · payment date {dayFull(run.lines[0]?.pay_date)} · {open} awaiting a decision · scored by model <span className="font-mono text-xs">{run.model_version}</span></>}
      >
        <Button asChild variant="outline"><Link href="/run">Payment run overview<ArrowRight /></Link></Button>
      </PageTitle>

      <section aria-label="Flagged summary" className="stagger mb-6 grid gap-3 sm:grid-cols-3">
        <FilterCard active={filter === "blocked"} onClick={() => setFilter("blocked")} tone="blocked" label="Blocked · locked until the case is resolved"
          value={<CountUp value={run.totals.blocked.count} />} sub={rs(run.totals.blocked.amount)} />
        <FilterCard active={filter === "review"} onClick={() => setFilter("review")} tone="review" label="Review · needs a second approver"
          value={<CountUp value={run.totals.review.count} />} sub={rs(run.totals.review.amount)} />
        <FilterCard active={filter === "allow"} onClick={() => setFilter("allow")} tone="allow" label="Allow · cleared by every engine"
          value={<CountUp value={run.totals.allow.count} />} sub={rs(run.totals.allow.amount)} />
      </section>

      <Card className="animate-rise-in overflow-hidden [animation-delay:150ms]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-base font-semibold"><Flag aria-hidden className="size-4 text-blocked" />Payment decisions <span className="text-xs font-normal text-muted-foreground">{lines.length} lines shown</span></div>
            <div className="relative w-full sm:w-64">
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input aria-label="Search payee, invoice or reason" placeholder="Search payee, invoice, reason" value={query} onChange={(e) => setQuery(e.target.value)} className="h-9 pl-9 pr-8" />
              {query && <button type="button" aria-label="Clear search" onClick={() => setQuery("")} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><X className="size-3.5" /></button>}
            </div>
          </div>
          <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
            <TabsList>
              <TabsTrigger value="flagged"><Flag />Flagged {count("flagged")}</TabsTrigger>
              <TabsTrigger value="blocked"><span className="size-2 rounded-full bg-blocked" />Blocked {count("blocked")}</TabsTrigger>
              <TabsTrigger value="review"><span className="size-2 rounded-full bg-review" />Review {count("review")}</TabsTrigger>
              <TabsTrigger value="allow"><span className="size-2 rounded-full bg-allow" />Allow {count("allow")}</TabsTrigger>
              <TabsTrigger value="all">All {run.lines.length}</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="text-xs text-muted-foreground">Click a line to see the evidence and the agent trace</div>
        </div>
        <Table aria-label="Payment decisions">
          <THead>
            <TR>
              <TH>Verdict</TH><TH>Score</TH><TH>Payee</TH><TH className="text-right">Amount</TH><TH>Top reason</TH><TH>Entered by</TH><TH>Status</TH><TH className="text-right">Action</TH>
            </TR>
          </THead>
          <TBody key={filter}>
            {lines.map((l, i) => (
              <TR key={l.id} tabIndex={0} aria-label={`${l.vendor}, ${rs(l.amount)}, ${l.decision}`}
                onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) setSheet(l.id); }}
                className={cn("row-in cursor-pointer hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none", l.decision === "blocked" && "bg-blocked-soft/30")}
                style={{ "--i": i } as React.CSSProperties} onClick={() => setSheet(l.id)}>
                <TD><DecisionBadge decision={l.decision} />{l.override && <div className="mt-1 text-[10px] text-review">overridden after case</div>}</TD>
                <TD><ScoreBar score={l.score} /></TD>
                <TD className="min-w-48">
                  <button type="button" onClick={(e) => { e.stopPropagation(); setSheet(l.id); }} aria-label={`Inspect ${l.vendor}, invoice ${l.invoice_no}`} className="text-left font-semibold transition-colors hover:text-accent">{l.vendor}</button>
                  <div className="text-xs text-muted-foreground">{l.invoice_no} · {l.bank_name} ••{l.bank_last4}{l.fraud_type && l.decision !== "allow" ? ` · ${FRAUD_NAMES[l.fraud_type]}` : ""}</div>
                </TD>
                <TD className="tabular whitespace-nowrap text-right font-medium">{rs(l.amount)}</TD>
                <TD className="min-w-56 max-w-[360px]">
                  <div className={cn("line-clamp-2 text-sm", l.decision === "allow" && "text-muted-foreground")}>{l.top_reason}</div>
                  {l.info.length > 0 && <div className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">{l.info[0]}</div>}
                </TD>
                <TD className="text-xs"><div className="whitespace-nowrap">{l.created_by}</div><div className="whitespace-nowrap text-muted-foreground">{dateTime(l.created_at)}</div></TD>
                <TD className="text-xs">
                  <span className={cn(l.status === "approved" && "text-allow", l.status === "blocked" && "text-blocked", l.status === "held" && "text-review")}>{STATUS_LABEL[l.status] ?? l.status}</span>
                  {l.approved_by && <div className="text-muted-foreground">by {l.approved_by}</div>}
                </TD>
                <TD className="text-right" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
                  <LineAction line={l} canApprove={canApprove} busy={busy} onApprove={() => act("approve", [l.id])} onReview={() => setReview(l)} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
        {lines.length === 0 && (
          <div className="flex animate-fade-in flex-col items-center gap-2 p-10 text-center text-sm text-muted-foreground">
            {query ? <>No lines match “{query}”. <button type="button" className="text-accent hover:underline" onClick={() => setQuery("")}>Clear search</button></>
              : filter === "flagged" ? <><CircleCheck className="size-6 text-allow" />Nothing flagged in this run. Every line was cleared by the engines.</>
                : "No lines match this verdict. Choose another filter."}
          </div>
        )}
      </Card>

      <ReviewDialog line={review} userId={user?.id} canApprove={canApprove} busy={!!busy}
        onClose={() => setReview(null)} onApprove={(note) => review && act("approve", [review.id], note)} onHold={(note) => review && act("hold", [review.id], note)} />
      <LineSheet paymentId={sheet} onClose={() => setSheet(null)} />
    </>
  );
}

function FilterCard({ active, onClick, tone, label, value, sub }: { active: boolean; onClick: () => void; tone: "blocked" | "review" | "allow"; label: string; value: React.ReactNode; sub: string }) {
  const ring = { blocked: "border-blocked/50 ring-blocked/15", review: "border-review/50 ring-review/15", allow: "border-allow/50 ring-allow/15" }[tone];
  const bar = { blocked: "bg-blocked", review: "bg-review", allow: "bg-allow" }[tone];
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
      className={cn("lift relative overflow-hidden rounded-lg border border-border bg-card p-5 text-left shadow-[var(--shadow-card)]", active && cn("ring-4", ring))}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1 transition-all duration-300", bar, active ? "opacity-100" : "opacity-40")} />
      <Stat label={label} value={value} sub={sub} tone={tone} />
    </button>
  );
}

function LineAction({ line: l, canApprove, busy, onApprove, onReview }: {
  line: RunLine; canApprove: boolean; busy: string | null; onApprove: () => void; onReview: () => void;
}) {
  if (l.decision === "blocked" && l.status === "blocked") {
    return (
      <div className="flex items-center justify-end gap-1.5">
        <Tooltip content="Blocked by Nigraan: this line cannot be released. Resolve the case first.">
          <span><Button size="sm" variant="outline" disabled aria-label="Release disabled" className="px-2.5"><Lock /></Button></span>
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
      <span><Button size="sm" variant="outline" disabled={!canApprove || !!busy} onClick={onApprove}>{busy === `approve${l.id}` ? <Loader2 className="animate-spin" /> : <CircleCheck />}Approve</Button></span>
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
            <Textarea aria-label="Second approval note" className="mt-4" placeholder="Note (e.g. called vendor on registered number, confirmed new account)" value={note} onChange={(e) => setNote(e.target.value)} />
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
