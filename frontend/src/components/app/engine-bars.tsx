import { ENGINE_LABEL } from "@/components/app/decision";

const ORDER = ["risk_model", "duplicate", "graph", "anomaly"];

/** Engine contributions to the fused score (w x signal), plus the raw signal of each engine. */
export function EngineBars({ contributions, signals }: { contributions: Record<string, number>; signals: Record<string, number> }) {
  const max = Math.max(0.05, ...ORDER.map((e) => contributions[e] ?? 0));
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-sm font-semibold">Engine contributions</div>
        <div className="text-[11px] text-muted-foreground">bar = weight × signal · label = raw signal</div>
      </div>
      <div className="grid gap-2">
        {ORDER.map((e) => (
          <div key={e} className="grid grid-cols-[minmax(0,150px)_1fr_44px] items-center gap-2 text-xs">
            <div className="text-muted-foreground">{ENGINE_LABEL[e]}</div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="grow-x h-full rounded-full bg-accent" style={{ width: `${(100 * (contributions[e] ?? 0)) / max}%` }} />
            </div>
            <div className="tabular text-right">{(signals[e] ?? 0).toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** SHAP-style feature contributions from the XGBoost model (log-odds). */
export function FeatureBars({ items }: { items: { name: string; value: number }[] }) {
  const max = Math.max(0.1, ...items.map((i) => Math.abs(i.value)));
  return (
    <div className="grid gap-1.5">
      {items.map((i) => (
        <div key={i.name} className="grid grid-cols-[minmax(0,180px)_1fr_48px] items-center gap-2 text-xs">
          <div className="truncate text-muted-foreground" title={i.name}>{i.name}</div>
          <div className="relative h-2 rounded-full bg-muted">
            <div className="absolute top-0 h-full w-px bg-border" style={{ left: "50%" }} />
            <div className={`absolute top-0 h-full rounded-full ${i.value >= 0 ? "grow-x bg-blocked/80" : "grow-x-r bg-allow/80"}`}
              style={i.value >= 0 ? { left: "50%", width: `${(50 * i.value) / max}%` } : { right: "50%", width: `${(50 * -i.value) / max}%` }} />
          </div>
          <div className="tabular text-right">{i.value >= 0 ? "+" : ""}{i.value.toFixed(2)}</div>
        </div>
      ))}
    </div>
  );
}
