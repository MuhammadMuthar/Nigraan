"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Brain, ClipboardList, Eye, FileUp, LayoutDashboard, Loader2, LogOut, RotateCcw, ShieldAlert, Users, Wallet, CalendarPlus,
} from "lucide-react";
import { api } from "@/lib/api";
import { ROLE_LABEL, useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { dayFull } from "@/lib/format";

const NAV = [
  { href: "/run", label: "Payment run", Icon: ClipboardList },
  { href: "/cases", label: "Cases", Icon: ShieldAlert },
  { href: "/upload", label: "Upload invoices", Icon: FileUp },
  { href: "/cash", label: "Cash outlook", Icon: Wallet },
  { href: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { href: "/vendors", label: "Vendors", Icon: Users },
];

type DemoStatus = { demo_mode: boolean; open_run_id: number | null; model_version: string; gemini: boolean; as_of: string | null };

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const [demo, setDemo] = useState<DemoStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);
  useEffect(() => {
    api.get<DemoStatus>("/demo/status").then(setDemo).catch(() => setDemo(null));
  }, [path]);

  if (!ready || !user) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 size-4 animate-spin" />Loading…</div>;
  }

  async function run(kind: "reset" | "week" | "retrain") {
    setBusy(kind);
    try {
      if (kind === "reset") {
        const r = await api.post<{ seconds: number }>("/demo/reset");
        toast.success(`Demo data reset (${r.seconds}s). Seeded company restored.`);
        window.location.href = "/run";
      } else if (kind === "week") {
        const r = await api.post<{ invoices: number; seconds: number; totals: Record<string, { count: number }> }>("/demo/load-week");
        toast.success(`Loaded ${r.invoices} invoices and scored them in ${r.seconds}s: ${r.totals.blocked.count} blocked, ${r.totals.review.count} to review.`);
        window.location.href = "/run";
      } else {
        const job = await api.post<{ id: string }>("/admin/retrain");
        toast.info("Retraining from case outcomes…");
        for (let i = 0; i < 120; i++) {
          await new Promise((r) => setTimeout(r, 1500));
          const s = await api.get<{ status: string; result?: { version: string; holdout: Record<string, number | string>; fraud_labels: number; new_case_labels: number }; message?: string }>(`/admin/retrain/${job.id}`);
          if (s.status === "done" && s.result) {
            const h = s.result.holdout;
            toast.success(`Model ${s.result.version} trained on ${s.result.fraud_labels} fraud labels (${s.result.new_case_labels} from your cases). Hold-out recall ${Math.round(Number(h.recall) * 100)}%, false alarms ${(Number(h.far) * 100).toFixed(1)}%.`, { duration: 9000 });
            break;
          }
          if (s.status === "failed") {
            toast.error(`Retrain failed: ${s.message}`);
            break;
          }
        }
        api.get<DemoStatus>("/demo/status").then(setDemo);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-border bg-card px-3 py-4 md:flex">
        <Link href="/run" className="mb-6 flex items-center gap-2 px-2">
          <div className="flex size-8 items-center justify-center rounded-md bg-accent text-white"><Eye className="size-4.5" /></div>
          <div>
            <div className="text-sm font-bold tracking-tight">Nigraan</div>
            <div className="text-[10px] text-muted-foreground">نگران · finance control tower</div>
          </div>
        </Link>
        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, Icon }) => (
            <Link key={href} href={href}
              className={cn("flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                path?.startsWith(href) && "bg-accent-soft font-medium text-accent hover:bg-accent-soft hover:text-accent")}>
              <Icon className="size-4" />{label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-2 px-2 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1.5"><Brain className="size-3.5" />Model {demo?.model_version ?? "…"}</div>
          <div>Document AI: {demo?.gemini ? "Gemini" : "PDF text + regex"}</div>
          <div>Synthetic data · fictional company</div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-card/90 px-4 backdrop-blur md:px-6">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">Bismillah Distributors <span className="font-normal text-muted-foreground">(fictional) · Lahore</span></div>
            <div className="text-xs text-muted-foreground">As of {dayFull(demo?.as_of ?? null)}</div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {demo?.demo_mode && (
              <div className="flex items-center gap-1 rounded-md border border-dashed border-accent/40 bg-accent-soft/60 px-1.5 py-1">
                <span className="px-1 text-[10px] font-semibold uppercase tracking-wide text-accent">Demo</span>
                <Tooltip content="Restore the seeded company (history only, no open run)">
                  <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run("reset")}>
                    {busy === "reset" ? <Loader2 className="animate-spin" /> : <RotateCcw />}Reset data
                  </Button>
                </Tooltip>
                <Tooltip content="Import this week's 40 invoices and score the payment run">
                  <Button size="sm" variant="ghost" disabled={!!busy || !!demo.open_run_id} onClick={() => run("week")}>
                    {busy === "week" ? <Loader2 className="animate-spin" /> : <CalendarPlus />}Load demo week
                  </Button>
                </Tooltip>
                <Tooltip content="Retrain the fraud models with the case outcomes you recorded">
                  <Button size="sm" variant="ghost" disabled={!!busy || user.role === "accountant"} onClick={() => run("retrain")}>
                    {busy === "retrain" ? <Loader2 className="animate-spin" /> : <Brain />}Retrain
                  </Button>
                </Tooltip>
              </div>
            )}
            <div className="hidden text-right sm:block">
              <div className="text-xs font-medium">{user.name}</div>
              <div className="text-[11px] text-muted-foreground">{ROLE_LABEL[user.role]}</div>
            </div>
            <Tooltip content="Sign out">
              <Button size="icon" variant="ghost" onClick={logout} aria-label="Sign out"><LogOut /></Button>
            </Tooltip>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-6">{children}</main>
      </div>
    </div>
  );
}

export function PageTitle({ title, sub, children }: { title: string; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {sub && <div className="mt-0.5 text-sm text-muted-foreground">{sub}</div>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
