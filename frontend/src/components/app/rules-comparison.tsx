import { Flag, GitCompareArrows, Minus } from "lucide-react";
import type { RulesComparison, RunRulesComparison } from "@/lib/types";
import { rs } from "@/lib/format";
import { Card } from "@/components/ui/card";

export function RulesComparisonSummary({ comparison }: { comparison?: RunRulesComparison }) {
  if (!comparison) return null;
  return (
    <Card className="mb-6 overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <h2 className="flex items-center gap-2 text-base font-semibold"><GitCompareArrows aria-hidden className="size-4 text-accent" />Compare this run with rule checks</h2>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Current payment lines, not an accuracy test. Nigraan combines learned duplicate, payment-risk and anomaly models with deterministic policy and relationship checks.</p>
      </div>
      <div className="grid gap-4 p-5 sm:grid-cols-2">
        {([comparison.simple, comparison.expert]).map((baseline) => (
          <div key={baseline.name} className="rounded-lg border border-border p-4">
            <h3 className="text-sm font-semibold">{baseline.name}</h3>
            <dl className="mt-3 grid gap-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-1">
                <dt className="text-muted-foreground">Flagged by these checks</dt>
                <dd className="tabular font-semibold">{baseline.flagged_count} lines · {rs(baseline.flagged_amount)}</dd>
              </div>
              <div className="border-t border-border pt-3">
                <dt className="text-xs text-muted-foreground">Flagged by Nigraan; no flag from these checks</dt>
                <dd className="tabular mt-1 text-lg font-semibold">{baseline.nigraan_additional_count} <span className="text-xs font-normal text-muted-foreground">lines · {rs(baseline.nigraan_additional_amount)}</span></dd>
              </div>
            </dl>
            <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">{baseline === comparison.simple ? "Approval-limit and prior invoice-number checks." : "Also checks bank changes, new vendors, payment timing, prices, split exposure and relationships."}</p>
          </div>
        ))}
      </div>
      <p className="border-t border-border bg-muted/30 px-5 py-3 text-xs leading-relaxed text-muted-foreground">{comparison.note} A flag is a reason to investigate; these comparisons do not grant payment approval or prove fraud.</p>
    </Card>
  );
}

export function LineRuleChecks({ comparison, detailed = false }: { comparison?: RulesComparison; detailed?: boolean }) {
  if (!comparison) return null;
  if (!detailed) {
    return (
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground" aria-label="Rule-check comparison">
        <span>Simple: {comparison.simple.flagged ? "flag" : "no flag"}</span>
        <span>Expert: {comparison.expert.flagged ? "flag" : "no flag"}</span>
      </div>
    );
  }
  return (
    <section aria-label="Rule-check comparison" className="grid gap-3">
      <div>
        <h3 className="text-sm font-semibold">Rule-check comparison</h3>
        <p className="mt-1 text-xs text-muted-foreground">These deterministic checks are compared separately with Nigraan&apos;s combined verdict.</p>
      </div>
      {([comparison.simple, comparison.expert]).map((baseline) => (
        <div key={baseline.name} className="rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{baseline.name}</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">{baseline.flagged ? <Flag aria-hidden className="size-3.5" /> : <Minus aria-hidden className="size-3.5" />}{baseline.flagged ? "Flags this line" : "No flag"}</span>
          </div>
          {baseline.checks.length > 0 ? <ul className="mt-2 grid gap-1.5 text-xs text-muted-foreground">{baseline.checks.map((check) => <li key={check.code} className="flex gap-2"><span aria-hidden>•</span><span>{check.text}</span></li>)}</ul> : <p className="mt-2 text-xs text-muted-foreground">None of this comparator&apos;s checks triggered. Approval controls still apply.</p>}
        </div>
      ))}
    </section>
  );
}
