"use client";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis,
} from "recharts";
import { CalendarClock, CircleCheck, Loader2, Play, TriangleAlert, Wallet, X } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { day, dayFull, pct, rs, rsShort } from "@/lib/format";
import type { Projection, ReceivableRow } from "@/lib/types";
import { PageTitle } from "@/components/app/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Empty, Skeleton, Stat } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Outlook = { projection: Projection; receivables: ReceivableRow[]; run_id: number | null; risk_label: string; risk_model: string; assumptions: string[]; basis_legend: Record<string, string> };
type ScenarioRes = { base: Projection; scenario: Projection; delta: { low_point_change: number; breach_before: string | null; breach_after: string | null; total_in_change: number } };

const k = (p: number) => p / 100;

export default function CashPage() {
  const { data, loading, error } = useApi<Outlook>("/cash/projection");
  const [week, setWeek] = useState<number | null>(null);
  const [moves, setMoves] = useState<{ receivable_id: number; customer: string; amount: number; from: string; new_date: string }[]>([]);
  const [holdYellow, setHoldYellow] = useState(false);
  const [scen, setScen] = useState<ScenarioRes | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const p = data?.projection;
  const focusWeek = week ?? (p ? (p.weeks.find((w) => w.low_day === p.low_point_day)?.week ?? 1) : 1);
  const weekly = useMemo(() => p?.weeks.map((w) => ({
    label: `W${w.week} ${day(w.start)}`, week: w.week,
    in_fact: k(w.inflow_by_basis.fact), in_estimate: k(w.inflow_by_basis.estimate), in_assumption: k(w.inflow_by_basis.assumption),
    out_fact: -k(w.outflow_by_basis.fact), out_assumption: -k(w.outflow_by_basis.assumption + w.outflow_by_basis.estimate),
    closing: k(w.closing), low: k(w.low),
  })) ?? [], [p]);
  const daily = useMemo(() => {
    if (!p?.days) return [];
    const w = p.weeks[focusWeek - 1];
    return p.days.filter((d) => d.day >= w.start && d.day <= w.end).map((d) => ({ label: day(d.day, { weekday: "short" }), inflow: k(d.inflow), outflow: -k(d.outflow), closing: k(d.closing) }));
  }, [p, focusWeek]);

  if (loading && !data) return <div className="grid gap-4"><Skeleton className="h-24" /><Skeleton className="h-80" /></div>;
  if (error || !data || !p) return <Empty icon={<Wallet />} title="Cash outlook unavailable">{error?.message}</Empty>;

  async function runScenario() {
    setBusy(true);
    try {
      const r = await api.post<ScenarioRes>("/cash/scenarios", { name: "What-if", moves: moves.map((m) => ({ receivable_id: m.receivable_id, new_date: m.new_date })), hold_yellow: holdYellow, run_id: data!.run_id });
      setScen(r);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const recs = data.receivables;
  const highRisk = [...recs].sort((a, b) => (b.risk ?? 0) * b.amount - (a.risk ?? 0) * a.amount);
  const shown = showAll ? recs : highRisk.slice(0, 15);
  const compare = scen ? scen.base.weeks.map((w, i) => ({ label: `W${w.week}`, base: k(w.low), scenario: k(scen.scenario.weeks[i].low) })) : [];

  return (
    <>
      <PageTitle title="Cash outlook" sub={`13 weeks from ${dayFull(p.as_of)} · deterministic cash engine · receipts dated by each customer's payment history`} />
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 text-xs">
        <span className="font-medium">Synthetic demo forecast · reserve checked daily</span><span className="text-muted-foreground">Facts, model estimates and assumptions are shown separately</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Card><CardContent className="pt-5"><Stat label="Cash today" value={rs(p.opening)} sub="bank balance (fact)" /></CardContent></Card>
        <Card><CardContent className="pt-5"><Stat label="Reserve" value={rs(p.reserve)} sub="minimum the owner wants to keep" /></CardContent></Card>
        <Card className="border-accent/25 bg-accent-soft/30"><CardContent className="pt-5"><Stat label="Lowest point" value={rs(p.low_point)} sub={dayFull(p.low_point_day)} tone={p.first_breach ? "blocked" : "accent"} /></CardContent></Card>
        <Card><CardContent className="pt-5"><Stat label="First reserve breach" value={p.first_breach ? day(p.first_breach, { weekday: "short" }) : "None"} sub={p.first_breach ? `short by ${rs(p.breach_gap)}` : "stays above reserve for 13 weeks"} tone={p.first_breach ? "blocked" : "allow"} /></CardContent></Card>
        <Card><CardContent className="pt-5"><Stat label="Next 13 weeks" value={<span className="text-base">+{rsShort(p.total_in)} / −{rsShort(p.total_out)}</span>} sub={`${p.beyond_horizon.length} receipt(s) beyond horizon`} /></CardContent></Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>13-week cash projection</CardTitle>
          <CardDescription>Bars: weekly receipts (above) and payments (below), split into facts, model estimates and assumptions. Lines: week-end balance and the daily low inside each week. Click a week for the daily view.</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={weekly} margin={{ top: 8, right: 16, left: 8, bottom: 0 }} onClick={(e) => { const w = (e as { activePayload?: { payload: { week: number } }[] })?.activePayload?.[0]?.payload?.week; if (w) setWeek(w); }}>
              <defs>
                <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" fill="#e6f4f2" /><line x1="0" y1="0" x2="0" y2="6" stroke="#0f766e" strokeWidth="2" />
                </pattern>
                <pattern id="hatchOut" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" fill="#e2e8f0" /><line x1="0" y1="0" x2="0" y2="6" stroke="#64748b" strokeWidth="2" />
                </pattern>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => rsShort(v * 100)} tick={{ fontSize: 10 }} width={60} tickLine={false} axisLine={false} />
              <RTooltip formatter={(v, n) => [rs(Math.abs(Number(v)) * 100), LEG[String(n)] ?? n]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Legend formatter={(v) => <span className="text-xs">{LEG[v] ?? v}</span>} />
              <ReferenceLine y={k(p.reserve)} stroke="#64748b" strokeDasharray="5 4" label={{ value: "Reserve", fontSize: 10, fill: "#58677b", position: "insideTopLeft" }} />
              <ReferenceLine y={0} stroke="#a1a1aa" />
              <Bar dataKey="in_fact" stackId="in" fill="#0f766e" />
              <Bar dataKey="in_estimate" stackId="in" fill="#5eb3aa" />
              <Bar dataKey="in_assumption" stackId="in" fill="url(#hatch)" />
              <Bar dataKey="out_fact" stackId="out" fill="#d4d4d8" />
              <Bar dataKey="out_assumption" stackId="out" fill="url(#hatchOut)" />
              <Line dataKey="closing" stroke="#18181b" strokeWidth={2} dot={{ r: 2.5 }} />
              <Line dataKey="low" stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted-foreground">
            {Object.entries(data.basis_legend).map(([b, t]) => <span key={b}><b className="capitalize">{b}:</b> {t}</span>)}
          </div>
        </CardContent>
      </Card>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader><CardTitle>Week {focusWeek}, day by day</CardTitle><CardDescription>{day(p.weeks[focusWeek - 1].start)} to {day(p.weeks[focusWeek - 1].end)} · the reserve check runs daily, so a mid-week dip is caught even if the week ends positive</CardDescription></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(v) => rsShort(v * 100)} tick={{ fontSize: 10 }} width={56} tickLine={false} axisLine={false} />
                <RTooltip formatter={(v, n) => [rs(Math.abs(Number(v)) * 100), String(n)]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <ReferenceLine y={k(p.reserve)} stroke="#64748b" strokeDasharray="5 4" />
                <Bar dataKey="inflow" fill="#5eb3aa" />
                <Bar dataKey="outflow" fill="#d4d4d8" />
                <Line dataKey="closing" stroke="#18181b" strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="mt-3 flex flex-wrap gap-1">
              {p.weeks.map((w) => (
                <button key={w.week} onClick={() => setWeek(w.week)} aria-pressed={w.week === focusWeek} aria-label={`Week ${w.week}${w.low < p.reserve ? ", below reserve" : ", above reserve"}`} className={cn("rounded-md px-2.5 py-2 text-xs", w.week === focusWeek ? "bg-accent text-white" : w.low < p.reserve ? "bg-blocked-soft text-blocked" : "bg-muted text-muted-foreground")}>W{w.week}</button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2"><CardTitle>What if…</CardTitle><Badge variant="outline">Scenario · no changes to the books</Badge></div>
            <CardDescription>Move a collection to a promised date, or hold the yellow lines of this run. Scenarios never change the books.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {moves.length === 0 && <div className="text-sm text-muted-foreground">Pick a receivable below and press <b>Move</b> to set a new collection date.</div>}
            {moves.map((m, i) => (
              <div key={m.receivable_id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
                <CalendarClock className="size-4 text-accent" />
                <span className="font-medium">{m.customer}</span><span className="tabular text-muted-foreground">{rs(m.amount)}</span>
                <span className="text-xs text-muted-foreground">expected {day(m.from)} →</span>
                <Input aria-label={`New collection date for ${m.customer}`} type="date" className="h-8 w-40" value={m.new_date} min={p.as_of} disabled={busy} onChange={(e) => { setMoves((xs) => xs.map((x, j) => (j === i ? { ...x, new_date: e.target.value } : x))); setScen(null); }} />
                <Button size="icon" variant="ghost" className="ml-auto size-7" disabled={busy} onClick={() => { setMoves((xs) => xs.filter((_, j) => j !== i)); setScen(null); }} aria-label="Remove"><X /></Button>
              </div>
            ))}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={holdYellow} onChange={(e) => { setHoldYellow(e.target.checked); setScen(null); }} disabled={busy || !data.run_id} />Hold the yellow lines of this week&apos;s run</label>
            <Button className="w-fit" onClick={runScenario} disabled={busy || (moves.length === 0 && !holdYellow)}>{busy ? <Loader2 className="animate-spin" /> : <Play />}Run scenario</Button>
            {scen && (
              <div className="grid gap-3 rounded-md border border-border p-3">
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div><div className="text-muted-foreground">Low point change</div><div className={cn("tabular text-base font-semibold", scen.delta.low_point_change >= 0 ? "text-allow" : "text-blocked")}>{scen.delta.low_point_change >= 0 ? "+" : ""}{rs(scen.delta.low_point_change)}</div></div>
                  <div><div className="text-muted-foreground">First breach: base</div><div className="text-base font-semibold">{scen.delta.breach_before ? day(scen.delta.breach_before) : "none"}</div></div>
                  <div><div className="text-muted-foreground">First breach: scenario</div><div className={cn("text-base font-semibold", scen.delta.breach_after ? "text-blocked" : "text-allow")}>{scen.delta.breach_after ? day(scen.delta.breach_after) : "none"}</div></div>
                </div>
                <div className="text-[11px] text-muted-foreground">Total receipts change: {rs(scen.delta.total_in_change)} (moving a collection changes timing, never the total)</div>
                <ResponsiveContainer width="100%" height={160}>
                  <LineChart data={compare} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis tickFormatter={(v) => rsShort(v * 100)} tick={{ fontSize: 10 }} width={56} tickLine={false} axisLine={false} />
                    <RTooltip formatter={(v, n) => [rs(Number(v) * 100), n === "base" ? "Base (weekly low)" : "Scenario (weekly low)"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <ReferenceLine y={k(p.reserve)} stroke="#64748b" strokeDasharray="5 4" />
                    <Line dataKey="base" stroke="#a1a1aa" strokeWidth={2} dot={false} />
                    <Line dataKey="scenario" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-semibold">Open receivables ({recs.length})</div>
            <div className="text-xs text-muted-foreground">{showAll ? "Sorted by expected date" : "Riskiest first (amount × late risk)"} · {data.risk_label} from the {data.risk_model?.toUpperCase()} model, predicted at issue date</div>
          </div>
          <Button size="sm" variant="outline" onClick={() => setShowAll(!showAll)}>{showAll ? "Show riskiest 15" : "Show all"}</Button>
        </div>
        <Table>
          <THead><TR><TH>Customer</TH><TH>Invoice</TH><TH className="text-right">Amount</TH><TH>Due</TH><TH>Expected</TH><TH>Late risk</TH><TH>Why</TH><TH /></TR></THead>
          <TBody>
            {shown.map((r) => (
              <TR key={r.receivable_id}>
                <TD><div className="font-medium">{r.customer}</div><div className="text-xs capitalize text-muted-foreground">{r.segment}</div></TD>
                <TD className="whitespace-nowrap text-xs">{r.invoice_no}</TD>
                <TD className="tabular whitespace-nowrap text-right">{rs(r.amount)}{(r.disputed ?? 0) > 0 && <div className="text-[10px] text-review">{rs(r.disputed ?? 0)} disputed (excluded)</div>}</TD>
                <TD className="text-xs">{day(r.due_date)}{(r.overdue_days ?? 0) > 0 && <div className="text-blocked">{r.overdue_days} days overdue</div>}</TD>
                <TD className="text-xs">{day(r.expected_date)}{r.basis === "assumption" && <Tooltip content={r.note ?? ""}><span><Badge variant="outline" className="ml-1">assumed</Badge></span></Tooltip>}</TD>
                <TD>
                  {r.limited_history ? <Badge variant="outline">Limited history</Badge> : (
                    <div className="flex items-center gap-1.5"><div className="h-1.5 w-12 overflow-hidden rounded-full bg-muted"><div className={cn("h-full", (r.risk ?? 0) >= 0.6 ? "bg-blocked" : (r.risk ?? 0) >= 0.35 ? "bg-review" : "bg-allow")} style={{ width: pct(r.risk) }} /></div><span className="tabular text-xs">{pct(r.risk)}</span></div>
                  )}
                </TD>
                <TD className="max-w-[300px] text-xs text-muted-foreground"><div className="line-clamp-2">{r.reasons.join(" · ") || "—"}</div></TD>
                <TD className="text-right">
                  <Button size="sm" variant="ghost" disabled={busy || moves.some((m) => m.receivable_id === r.receivable_id)}
                    onClick={() => { setMoves((xs) => [...xs, { receivable_id: r.receivable_id!, customer: r.customer, amount: r.amount, from: r.expected_date!, new_date: nextWeekday(p.as_of, 3) }]); setScen(null); }}>Move</Button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>

      <Card className="mt-5">
        <CardHeader><CardTitle>Assumptions</CardTitle></CardHeader>
        <CardContent><ul className="grid gap-1 text-sm text-muted-foreground">{data.assumptions.map((a, i) => <li key={i} className="flex gap-2">{i === 0 ? <TriangleAlert className="mt-0.5 size-4 shrink-0 text-review" /> : <CircleCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}{a}</li>)}</ul></CardContent>
      </Card>
    </>
  );
}

const LEG: Record<string, string> = {
  in_fact: "Receipts: fact", in_estimate: "Receipts: model estimate", in_assumption: "Receipts: assumption",
  out_fact: "Payments: fact", out_assumption: "Payments: assumption", closing: "Week-end balance", low: "Lowest daily balance",
};

function nextWeekday(asOf: string, plus: number): string {
  const d = new Date(`${asOf}T12:00:00`);
  d.setDate(d.getDate() + plus);
  return d.toISOString().slice(0, 10);
}
