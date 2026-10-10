"use client";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton-shimmer rounded-md bg-muted", className)} {...props} />;
}

export function Separator({ className }: { className?: string }) {
  return <div className={cn("h-px w-full bg-border", className)} />;
}

export function Empty({ icon, title, children }: { icon?: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex animate-rise-in flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card px-6 py-16 text-center">
      {icon && <div className="flex size-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground [&_svg]:size-7">{icon}</div>}
      <div className="text-sm font-semibold">{title}</div>
      {children && <div className="max-w-md text-sm leading-relaxed text-muted-foreground">{children}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "allow" | "review" | "blocked" | "accent" }) {
  const color = tone ? { allow: "text-allow", review: "text-review", blocked: "text-blocked", accent: "text-accent" }[tone] : "";
  return (
    // sized to its own card (container query), so narrow grids don't wrap the amount
    <div className="@container flex flex-col gap-1">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={cn("tabular text-[clamp(1.25rem,13cqi,1.875rem)] font-semibold tracking-tight", color)}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function motionOk() {
  if (typeof window === "undefined") return false;
  return !document.documentElement.classList.contains("reduce-motion") && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Counts up to `value` when it first appears or changes (respects reduced motion and the in-app animation switch). */
export function CountUp({ value, format = (n) => String(Math.round(n)), duration = 900 }: { value: number; format?: (n: number) => string; duration?: number }) {
  const [shown, setShown] = React.useState<number | null>(() => (motionOk() ? 0 : null));
  const displayed = React.useRef<number>(motionOk() ? 0 : value);
  React.useEffect(() => {
    const start = displayed.current;
    if (start === value) return;
    let raf = 0;
    if (!motionOk()) {
      raf = requestAnimationFrame(() => {
        displayed.current = value;
        setShown(null);
      });
      return () => cancelAnimationFrame(raf);
    }
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const v = start + (value - start) * (1 - Math.pow(1 - p, 3));
      displayed.current = p < 1 ? v : value;
      setShown(p < 1 ? v : null);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{format(shown ?? value)}</>;
}
