"use client";
import Link from "next/link";
import { Area, AreaChart, CartesianGrid, Line, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, CircleCheck, Hourglass, ShieldCheck, TriangleAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { day, dayFull, pct, rs, rsShort } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CashPanel as Panel, RunDetail } from "@/lib/types";

function Outcome({ title, sub, c, reserve, good }: { title: string; sub: string; c: Panel["with_nigraan"]; reserve: number; good: boolean }) {
  const ok = c.stays_above_reserve;
  return (
    <div className={cn("flex-1 rounded-lg border p-4", ok ? "border-allow/30 bg-allow-soft/60" : "border-blocked/30 bg-blocked-soft/60")}>
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5 text-sm font-semibold">{good && <ShieldCheck className="size-4 text-accent" />}{title}</div>
          <div className="text-xs text-muted-foreground">{sub}</div>
        </div>
        {ok ? <Badge variant="allow"><CircleCheck className="size-3.5" />Above reserve</Badge> : <Badge variant="blocked"><TriangleAlert className="size-3.5" />Breach</Badge>}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div className="text-[11px] text-muted-foreground">Cash low point (13 weeks)</div>
          <div className={cn("tabular text-xl font-semibold", ok ? "text-foreground" : "text-blocked")}>{rs(c.low_point)}</div>
          <div className="text-[11px] text-muted-foreground">on {dayFull(c.low_point_day)}</div>
        </div>
        <div>
          <div className="text-[11px] text-muted-foreground">First reserve breach</div>
          {c.first_breach ? (
            <>
              <div className="tabular text-xl font-semibold text-blocked">{day(c.first_breach, { weekday: "short" })}</div>
              <div className="text-[11px] text-blocked">short by {rs(c.breach_gap)} at the low point</div>
            </>
          ) : (
            <>
              <div className="text-xl font-semibold text-allow">None</div>
              <div className="text-[11px] text-muted-foreground">stays above {rs(reserve)}</div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function CashPanel({ run }: { run: RunDetail }) {
  const c = run.cash;
  const t = run.totals;
  const chart = c.chart.map((d) => ({ ...d, label: day(d.day), with_nigraan: d.with_nigraan / 100, release_everything: d.release_everything / 100 }));
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
        <div>
          <div className="text-sm font-semibold">Cash impact of this run</div>
          <div className="text-xs text-muted-foreground">Where the fraud firewall and the cash forecast meet: does cash stay above the reserve after this run?</div>
        </div>
        <div className="text-xs text-muted-foreground">Reserve <span className="tabular font-semibold text-foreground">{rs(c.reserve)}</span></div>
      </div>
      <div className="grid gap-5 p-5 xl:grid-cols-[260px_1fr_1fr]">
        <div className="grid content-start gap-3">
          <div>
            <div className="text-xs text-muted-foreground">Cash in bank before the run</div>
            <div className="tabular text-2xl font-semibold">{rs(c.cash_before_run)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">This run ({run.lines.length} lines)</div>
            <div className="tabular text-lg font-semibold">{rs(c.run_total)}</div>
            <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
              {(["allow", "review", "blocked"] as const).map((k) => (
                <div key={k} className={k === "allow" ? "bg-allow" : k === "review" ? "bg-review" : "bg-blocked"}
                  style={{ width: `${(100 * t[k].amount) / Math.max(1, c.run_total)}%` }} />
              ))}
            </div>
            <div className="mt-2 grid gap-1 text-xs">
              <div className="flex justify-between"><span className="text-allow">● Allow · {t.allow.count}</span><span className="tabular">{rs(t.allow.amount)}</span></div>
              <div className="flex justify-between"><span className="text-review">● Review · {t.review.count}</span><span className="tabular">{rs(t.review.amount)}</span></div>
              <div className="flex justify-between"><span className="text-blocked">● Blocked · {t.blocked.count}</span><span className="tabular">{rs(t.blocked.amount)}</span></div>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row xl:col-span-1 xl:flex-col">
          <Outcome title="With Nigraan" sub="Red lines blocked, green + yellow released" c={c.with_nigraan} reserve={c.reserve} good />
          <Outcome title="If every line were released" sub="No fraud firewall" c={c.release_everything} reserve={c.reserve} good={false} />
        </div>
        <div className="min-h-[220px]">
          <div className="mb-1 text-xs font-medium text-muted-foreground">Daily cash, next 4 weeks</div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chart} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={6} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => rsShort(v * 100)} tick={{ fontSize: 10 }} width={54} tickLine={false} axisLine={false} />
              <RTooltip formatter={(v, n) => [rs(Number(v) * 100), n === "with_nigraan" ? "With Nigraan" : "Release everything"]} labelStyle={{ fontSize: 12 }} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <ReferenceLine y={c.reserve / 100} stroke="var(--blocked)" strokeDasharray="4 4" label={{ value: "Reserve", position: "insideTopRight", fontSize: 10, fill: "var(--blocked)" }} />
              <Area type="stepAfter" dataKey="with_nigraan" stroke="var(--accent)" fill="var(--accent-soft)" strokeWidth={2} />
              <Line type="stepAfter" dataKey="release_everything" stroke="var(--blocked)" strokeWidth={1.5} strokeDasharray="5 3" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      {c.responsible_receivables.length > 0 && (
        <div className="border-t border-border bg-muted/40 px-5 py-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold"><Hourglass className="size-3.5 text-review" />Receivables most responsible for the low point (due before it, expected after it)</div>
            <Link href="/cash" className="flex items-center gap-1 text-xs font-medium text-accent hover:underline">Cash outlook<ArrowRight className="size-3" /></Link>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            {c.responsible_receivables.map((r) => (
              <div key={r.receivable_id} className="rounded-md border border-border bg-card px-3 py-2 text-xs">
                <div className="flex justify-between gap-2"><span className="truncate font-medium">{r.customer}</span><span className="tabular font-semibold">{rs(r.amount)}</span></div>
                <div className="mt-0.5 text-muted-foreground">Due {day(r.due_date)} · expected {day(r.expected_date)} · late risk {r.limited_history ? "n/a (limited history)" : pct(r.risk)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
