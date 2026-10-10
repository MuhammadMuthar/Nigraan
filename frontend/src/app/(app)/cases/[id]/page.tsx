"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeft, Ban, CircleCheck, Copy, FileText, Landmark, Languages, Loader2, Network, ShieldCheck, Sparkles, TriangleAlert, Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { dateTime, day, rs } from "@/lib/format";
import type { Reason, TraceStep } from "@/lib/types";
import { DecisionBadge, ENGINE_LABEL, FRAUD_NAMES, ScoreGauge } from "@/components/app/decision";
import { EngineBars, FeatureBars } from "@/components/app/engine-bars";
import { GraphView } from "@/components/app/graph-view";
import { AgentTrace } from "@/components/app/trace";
import { LABEL } from "@/components/app/feature-labels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Empty, Skeleton } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

type InvSummary = { id: number; invoice_no: string; vendor: string; invoice_date: string; received_at: string; total: number; status: string; lines: { description: string; qty: number; unit_price: number }[] };
type BankRow = { id: number; bank: string; last4: string; valid_from: string; valid_to: string | null; changed_by: string | null; approved_by: string | null; source: string; blocked: boolean; current_for_payment: boolean };
type Evidence = {
  duplicate: null | { prob: number; hard: boolean; features: Record<string, number>; this: InvSummary; match: InvSummary };
  graph: { signal: number; links: { weight: number; text: string; path: { id: string; kind: string; label: string }[] }[]; path: { id: string }[] };
  bank: { history: BankRow[] };
  rules: { code: string; text: string; hard: boolean }[];
  risk_model: { p: number; top: { feature: string; text: string; contribution: number }[]; contributions: Record<string, number> };
  anomaly: { signal: number };
  features: Record<string, number | null>;
};
type CaseDetail = {
  id: number; status: string; fraud_type: string | null; source: string; opened_at: string; resolved_at: string | null; resolved_by: string | null;
  amount: number; vendor: string; vendor_id: number; invoice_no: string; run_id: number | null;
  payment: { id: number; amount: number; status: string; created_by: string; created_at: string; pay_date: string; bank_name: string; bank_last4: string; override: string | null };
  invoice: { invoice_no: string; invoice_date: string; due_date: string; total: number; tax: number; source: string; file_name: string | null; lines: { description: string; qty: number; unit_price: number; amount: number }[] };
  vendor_info: { name: string; ntn: string | null; category: string; phone: string; address: string; status: string; created_at: string; related_party_note: string | null };
  score: null | { score: number; decision: string; reasons: Reason[]; engines: { signals: Record<string, number>; contributions: Record<string, number> }; evidence: Evidence; trace: TraceStep[]; model_version: string; scored_at: string };
  graph: { nodes: { id: string; kind: string; label: string }[]; edges: { source: string; target: string }[] };
  events: { at: string; user: string | null; kind: string; detail: Record<string, unknown> }[];
  verification: string;
};
type Summary = { mode: string; text: string | null; evidence: Record<string, unknown> | null; guardrail?: string };

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { data: c, loading, error, reload } = useApi<CaseDetail>(`/cases/${id}`);
  const [resolve, setResolve] = useState<null | "confirmed_fraud" | "false_alarm">(null);

  if (loading && !c) return <div className="grid gap-4"><Skeleton className="h-28" /><Skeleton className="h-96" /></div>;
  if (error || !c) return <Empty icon={<TriangleAlert />} title="Case not found">{error?.message}</Empty>;
  const s = c.score;
  const canResolve = c.status === "open" && (user?.role === "approver" || user?.role === "owner");
  const ev = s?.evidence;

  return (
    <>
      <Link href={c.run_id ? "/run" : "/cases"} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Back</Link>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-muted/40 px-6 py-3 text-xs">
          <span className="font-semibold uppercase tracking-wider text-muted-foreground">Investigation / Case #{c.id}</span>
          <span className="text-muted-foreground">Synthetic company · evidence-led review</span>
        </div>
        <div className="flex flex-wrap items-center gap-6 p-6">
          <div className="border-r border-border pr-6">
            <div className="mb-2 text-xs font-medium text-muted-foreground">{c.payment.status === "blocked" ? "Amount blocked" : "Payment amount"}</div>
            <div className="tabular text-2xl font-semibold tracking-tight">{rs(c.amount)}</div>
            <div className="mt-2 text-xs capitalize text-muted-foreground">{c.payment.status.replaceAll("_", " ")}</div>
          </div>
          {s && <ScoreGauge score={s.score} decision={s.decision} />}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold">{c.vendor}</h1>
              {s && <DecisionBadge decision={c.payment.override ? "review" : s.decision} />}
              <Badge variant={c.status === "open" ? "blocked" : c.status === "false_alarm" ? "allow" : "default"}>
                {c.status === "open" ? "Case open" : c.status === "false_alarm" ? "False alarm" : "Confirmed fraud"}
              </Badge>
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              Case #{c.id} · {rs(c.amount)} · invoice {c.invoice_no} · suspected <b className="text-foreground">{c.fraud_type ? FRAUD_NAMES[c.fraud_type] : "—"}</b>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              Entered by {c.payment.created_by} at {dateTime(c.payment.created_at)} · pays {c.payment.bank_name} ••{c.payment.bank_last4}
              {s && <> · scored {dateTime(s.scored_at)} by model <span className="font-mono">{s.model_version}</span></>}
            </div>
          </div>
          {c.status === "open" ? (
            <div className="flex gap-2">
              <Button variant="danger" disabled={!canResolve} onClick={() => setResolve("confirmed_fraud")}><Ban />Confirm fraud</Button>
              <Button variant="outline" disabled={!canResolve} onClick={() => setResolve("false_alarm")}><CircleCheck />False alarm</Button>
            </div>
          ) : (
            <div className="text-right text-xs text-muted-foreground">Resolved by {c.resolved_by ?? "audit"}<br />{dateTime(c.resolved_at)}</div>
          )}
        </div>
        {!canResolve && c.status === "open" && <div className="border-t border-border bg-muted/50 px-5 py-2 text-xs text-muted-foreground">Sign in as the approver or owner to resolve this case.</div>}
      </Card>

      {!s ? (
        <Card className="mt-5"><CardContent className="pt-5 text-sm text-muted-foreground">This case was found in the internal audit before Nigraan was installed. It is used as a training label; no score was recorded at the time.</CardContent></Card>
      ) : (
        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_350px]">
          <div className="grid min-w-0 content-start gap-5">
            <Card>
              <CardHeader><CardTitle>Why Nigraan stopped this payment</CardTitle><CardDescription>Plain-English reasons from each engine, strongest evidence first</CardDescription></CardHeader>
              <CardContent className="grid gap-3">
                {s.reasons.filter((r) => r.engine !== "info").map((r, i) => (
                  <div key={i} className={cn("flex flex-wrap items-start gap-2 rounded-lg p-3 text-sm leading-relaxed", i === 0 ? "border border-border bg-muted/50 font-medium" : "bg-muted/20")}>
                    <Badge variant={r.engine === "rules" ? "blocked" : "accent"} className="mt-0.5 shrink-0">{ENGINE_LABEL[r.engine] ?? r.engine}</Badge>
                    <span>{r.text}</span>
                  </div>
                ))}
                {s.reasons.filter((r) => r.engine === "info").map((r, i) => <div key={`i${i}`} className="text-xs text-muted-foreground">{r.text}</div>)}
              </CardContent>
            </Card>

            <Card className="border-accent/25">
              <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4 text-accent" />Suggested verification</CardTitle><CardDescription>Complete this check before recording a case outcome.</CardDescription></CardHeader>
              <CardContent className="text-sm leading-relaxed">{c.verification}</CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Evidence</CardTitle><CardDescription>Source records and model signals. Check the invoice, bank timeline and relationship paths.</CardDescription></CardHeader>
              <CardContent>
                <Tabs defaultValue={defaultTab(ev!)}>
                  <TabsList>
                    <TabsTrigger value="dup"><Copy />Duplicate</TabsTrigger>
                    <TabsTrigger value="bank"><Landmark />Bank history</TabsTrigger>
                    <TabsTrigger value="graph"><Network />Relationships</TabsTrigger>
                    <TabsTrigger value="invoice"><FileText />Invoice</TabsTrigger>
                  </TabsList>
                  <TabsContent value="dup"><DuplicateEvidence ev={ev!} /></TabsContent>
                  <TabsContent value="bank"><BankTimeline rows={ev!.bank.history} payDate={c.payment.created_at} /></TabsContent>
                  <TabsContent value="graph">
                    {ev!.graph.links.length > 0 && <div className="mb-3 rounded-md bg-blocked-soft px-3 py-2 text-sm text-blocked">{ev!.graph.links[0].text} <span className="text-xs">(signal {ev!.graph.signal.toFixed(2)})</span></div>}
                    {c.vendor_info.related_party_note && <div className="mb-3 rounded-md bg-muted px-3 py-2 text-xs">{c.vendor_info.related_party_note}</div>}
                    <GraphView nodes={c.graph.nodes} edges={c.graph.edges} path={(ev!.graph.path ?? []).map((p) => p.id)} />
                    <div className="mt-2 flex gap-4 text-[11px] text-muted-foreground"><span><span className="mr-1 inline-block size-2 rounded-full bg-accent" />vendor</span><span><span className="mr-1 inline-block size-2 rounded-full bg-blocked" />employee</span><span><span className="mr-1 inline-block size-2 rounded-full bg-zinc-500" />identifier (phone, bank, address)</span></div>
                  </TabsContent>
                  <TabsContent value="invoice"><InvoiceView c={c} /></TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>How the score was built</CardTitle><CardDescription>score = 100 × max(rule, Σ weight × engine signal), bands at 40 and 75</CardDescription></CardHeader>
              <CardContent className="grid gap-6 2xl:grid-cols-2">
                <EngineBars contributions={s.engines.contributions} signals={s.engines.signals} />
                <div>
                  <div className="mb-2 text-sm font-semibold">Risk model drivers (SHAP, log-odds)</div>
                  <FeatureBars items={Object.entries(ev!.risk_model.contributions).slice(0, 8).map(([k, v]) => ({ name: LABEL[k] ?? k, value: v }))} />
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid content-start gap-5">
            <SummaryCard caseId={c.id} />
            <Card><CardContent className="pt-5"><AgentTrace steps={s.trace} /></CardContent></Card>
            <Card>
              <CardHeader><CardTitle>Case outcome & audit log</CardTitle></CardHeader>
              <CardContent className="grid gap-2 text-xs">
                {c.events.filter((e) => e.kind !== "viewed").map((e, i) => (
                  <div key={i} className="flex justify-between gap-2"><span><b className="capitalize">{e.kind.replace("_", " ")}</b>{e.user ? ` by ${e.user}` : " by Nigraan"}{typeof e.detail?.note === "string" && e.detail.note ? `: "${e.detail.note}"` : ""}</span><span className="shrink-0 text-muted-foreground">{dateTime(e.at)}</span></div>
                ))}
                <div className="text-muted-foreground">Viewed {c.events.filter((e) => e.kind === "viewed").length} time(s) (audit-logged)</div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      <ResolveDialog caseId={c.id} outcome={resolve} onClose={() => setResolve(null)} onDone={() => { setResolve(null); reload(); }} />
    </>
  );
}

function defaultTab(ev: Evidence): string {
  if (ev.duplicate && ev.duplicate.prob >= 0.5) return "dup";
  if (ev.graph.signal >= 0.3) return "graph";
  if (ev.bank.history.length > 1 && (ev.features.days_since_bank_change ?? 999) < 60 && ev.features.account_changed) return "bank";
  return "invoice";
}

function Side({ inv, title }: { inv: InvSummary; title: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <div className="mt-1 font-mono text-base font-semibold">{inv.invoice_no}</div>
      <div className="text-xs text-muted-foreground">{inv.vendor} · dated {day(inv.invoice_date, { year: "numeric" })} · {inv.status}</div>
      <div className="tabular mt-2 text-lg font-semibold">{rs(inv.total)}</div>
      <div className="mt-2 grid gap-0.5 text-xs">
        {inv.lines.map((l, i) => <div key={i} className="flex justify-between gap-2"><span className="truncate">{l.description}</span><span className="tabular shrink-0">{l.qty} × {rs(l.unit_price)}</span></div>)}
      </div>
    </div>
  );
}

function DuplicateEvidence({ ev }: { ev: Evidence }) {
  const d = ev.duplicate;
  if (!d) return <div className="py-6 text-sm text-muted-foreground">No earlier invoice from this vendor within ±90 days and ±2% of the amount.</div>;
  const f = d.features;
  return (
    <div>
      <div className={cn("mb-3 rounded-md px-3 py-2 text-sm", d.prob >= 0.5 ? "bg-blocked-soft text-blocked" : "bg-muted text-muted-foreground")}>
        {d.hard ? "Exact duplicate: same vendor, same invoice number (after normalising) and same total." : `Duplicate probability ${(d.prob * 100).toFixed(0)}% (logistic regression on pair features).`}
      </div>
      <div className="grid gap-3 md:grid-cols-2"><Side inv={d.this} title="This invoice" /><Side inv={d.match} title="Earlier invoice" /></div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
        <Fact k="Number similarity" v={`${(f.num_sim * 100).toFixed(0)}%${f.num_exact ? " (identical normalised)" : ""}`} />
        <Fact k="Days apart" v={f.date_gap.toFixed(0)} />
        <Fact k="Amount difference" v={`${f.amount_diff_pct.toFixed(2)}%`} />
        <Fact k="Same line items" v={`${(f.line_jaccard * 100).toFixed(0)}%`} />
      </div>
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return <div className="rounded-md bg-muted px-2.5 py-1.5"><div className="text-muted-foreground">{k}</div><div className="tabular font-semibold">{v}</div></div>;
}

function BankTimeline({ rows, payDate }: { rows: BankRow[]; payDate: string }) {
  if (!rows.length) return null;
  return (
    <ol className="relative ml-2 border-l border-border">
      {rows.map((r) => (
        <li key={r.id} className="mb-4 ml-4">
          <span className={cn("absolute -left-[6px] mt-1 size-3 rounded-full border-2 border-card", r.current_for_payment ? "bg-blocked" : "bg-zinc-400")} />
          <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {r.bank} ••{r.last4}
            {r.current_for_payment && <Badge variant="blocked">this payment</Badge>}
            {r.blocked && <Badge variant="default">blocked later</Badge>}
            <Badge variant="outline">{r.source.replace("_", " ")}</Badge>
          </div>
          <div className="text-xs text-muted-foreground">
            From {dateTime(r.valid_from)}{r.valid_to ? ` to ${dateTime(r.valid_to)}` : ""} · set by {r.changed_by ?? "—"} · second approval: {r.approved_by ?? <span className="font-semibold text-blocked">none</span>}
          </div>
        </li>
      ))}
      <li className="ml-4 text-xs text-muted-foreground"><span className="absolute -left-[6px] mt-0.5 size-3 rounded-full border-2 border-card bg-accent" />Payment entered {dateTime(payDate)}</li>
    </ol>
  );
}

function InvoiceView({ c }: { c: CaseDetail }) {
  return (
    <div className="grid gap-3 text-sm">
      <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
        <Fact k="Invoice" v={c.invoice.invoice_no} /><Fact k="Dated" v={day(c.invoice.invoice_date, { year: "numeric" })} />
        <Fact k="Due" v={day(c.invoice.due_date, { year: "numeric" })} /><Fact k="Source" v={c.invoice.source} />
      </div>
      <table className="w-full text-xs">
        <thead className="text-muted-foreground"><tr><th className="py-1 text-left font-medium">Line</th><th className="text-right font-medium">Qty</th><th className="text-right font-medium">Rate</th><th className="text-right font-medium">Amount</th></tr></thead>
        <tbody>{c.invoice.lines.map((l, i) => <tr key={i} className="border-t border-border"><td className="py-1.5">{l.description}</td><td className="tabular text-right">{l.qty}</td><td className="tabular text-right">{rs(l.unit_price)}</td><td className="tabular text-right">{rs(l.amount)}</td></tr>)}</tbody>
      </table>
      <div className="text-right text-xs">Tax {rs(c.invoice.tax)} · <b>Total {rs(c.invoice.total)}</b></div>
      <div className="rounded-md bg-muted px-3 py-2 text-xs"><b>{c.vendor_info.name}</b> · {c.vendor_info.category} · NTN {c.vendor_info.ntn ?? "none"} · {c.vendor_info.phone} · {c.vendor_info.address} · vendor since {day(c.vendor_info.created_at, { year: "numeric" })}</div>
    </div>
  );
}

function SummaryCard({ caseId }: { caseId: number }) {
  const [lang, setLang] = useState<"en" | "ur">("en");
  const key = `${caseId}-${lang}`;
  const [res, setRes] = useState<{ key: string; s: Summary } | null>(null);
  useEffect(() => {
    api.get<Summary>(`/cases/${caseId}/summary?lang=${lang}`)
      .then((s) => setRes({ key: `${caseId}-${lang}`, s }))
      .catch(() => setRes({ key: `${caseId}-${lang}`, s: { mode: "error", text: null, evidence: null } }));
  }, [caseId, lang]);
  const s = res && res.key === key ? res.s : null;
  const modeLabel: Record<string, string> = { llm: "LLM summary", llm_cached: "LLM summary (cached)", template: "Template (no LLM key)", evidence_only: "Evidence only", error: "Unavailable" };
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-1.5"><Sparkles className="size-4 text-accent" />Case summary</CardTitle>
          <Button size="sm" variant="ghost" onClick={() => setLang(lang === "en" ? "ur" : "en")}><Languages />{lang === "en" ? "Roman Urdu" : "English"}</Button>
        </div>
        <CardDescription>Explanation only; this summary does not determine the risk score. Numbers are checked against structured evidence.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {!s ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Loading explanation…</div> : (
          <>
            <Badge variant="outline" className="w-fit">{modeLabel[s.mode] ?? s.mode}</Badge>
            {s.text ? <p className="whitespace-pre-line text-sm leading-relaxed">{s.text}</p> : s.evidence && (
              <ul className="list-disc pl-4 text-sm">{((s.evidence.reasons as string[]) ?? []).map((r, i) => <li key={i}>{r}</li>)}</ul>
            )}
            {s.mode === "error" && <p role="alert" className="text-sm text-muted-foreground">The explanation is unavailable. Use the evidence and verification step to investigate.</p>}
            {s.guardrail && <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><ShieldCheck className="size-3.5" />{s.guardrail}</div>}
          </>
        )}

      </CardContent>
    </Card>
  );
}

function ResolveDialog({ caseId, outcome, onClose, onDone }: { caseId: number; outcome: null | "confirmed_fraud" | "false_alarm"; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [block, setBlock] = useState(true);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    try {
      await api.post(`/cases/${caseId}/resolve`, { outcome, note, block_vendor: outcome === "confirmed_fraud" && block });
      toast.success(outcome === "confirmed_fraud" ? "Confirmed as fraud. The payment is rejected and the outcome is saved as a training label." : "Marked as a false alarm. The line now needs a second approver; the label feeds the next retrain.");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={!!outcome} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>{outcome === "confirmed_fraud" ? "Confirm fraud" : "Mark as false alarm"}</DialogTitle>
        <DialogDescription>
          {outcome === "confirmed_fraud" ? "The payment will be rejected. The model's score stays on record." : "The red verdict stays on record; an override sends the line to a second approver."}
        </DialogDescription>
        <Textarea aria-label="Verification note" className="mt-4" placeholder="What did you verify? (required for the audit trail)" value={note} onChange={(e) => setNote(e.target.value)} />
        {outcome === "confirmed_fraud" && (
          <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={block} onChange={(e) => setBlock(e.target.checked)} />Block this vendor</label>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant={outcome === "confirmed_fraud" ? "danger" : "default"} disabled={busy || note.trim().length < 3} onClick={submit}>
            {busy && <Loader2 className="animate-spin" />}{outcome === "confirmed_fraud" ? <Ban /> : <Workflow />}Save outcome
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
