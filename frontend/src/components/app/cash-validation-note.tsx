import { CalendarClock, Info } from "lucide-react";
import { day, rs } from "@/lib/format";
import type { CashValidation, CollectionPolicy } from "@/lib/types";

export function CashValidationNote({ validation, compact = false }: { validation: CashValidation; compact?: boolean }) {
  const origins = validation.origins;
  return (
    <div className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
      <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <div>
        <span className="font-medium text-foreground">{validation.forecast_horizon_weeks}-week projection.</span>{" "}
        {validation.backtest_horizon_weeks ? <>{validation.backtest_horizon_weeks}-week receipt backtest on synthetic history{origins.length > 0 && <> · {origins.length} origins</>}.</> : <>Receipt backtest unavailable.</>}{" "}
        {validation.current_policy_backtested ? <>Later weeks and full reserve outcomes are unvalidated.</> : <>The current collection policy has not been backtested; saved errors describe the earlier next-week assumption.</>}
        {!compact && origins.length > 0 && <div className="mt-1">Backtest origins {day(origins[0])}–{day(origins.at(-1))} · seed {validation.seed ?? "unavailable"}{validation.current_policy_backtested && validation.mae_rupees_per_week !== null && <> · weekly receipt error {rs(Math.round(validation.mae_rupees_per_week * 100))}</>}</div>}
      </div>
    </div>
  );
}

export function UnconfirmedCollections({ policy, compact = false }: { policy: CollectionPolicy; compact?: boolean }) {
  if (policy.unconfirmed_count === 0) return null;
  return (
    <div className="flex gap-2 rounded-lg border border-border bg-muted/40 px-3 py-3 text-xs leading-relaxed">
      <CalendarClock className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div>
        <span className="font-semibold">{rs(policy.unconfirmed_amount)} across {policy.unconfirmed_count} overdue receivables has no supported collection date.</span>{" "}
        Excluded from base cash.{!compact && <> Use <b>Assume date</b> below to assess a collection in What-if; the books stay unchanged.</>}
      </div>
    </div>
  );
}
