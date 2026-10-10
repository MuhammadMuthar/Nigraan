"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ChevronDown, Menu, ShieldCheck, Brain, ClipboardList, Eye, FileUp, LayoutDashboard, Loader2, LogOut, RotateCcw, ShieldAlert, Users, Wallet, CalendarPlus,
} from "lucide-react";
import { api } from "@/lib/api";
import { ROLE_LABEL, useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import * as Popover from "@radix-ui/react-popover";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
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
  const [navOpen, setNavOpen] = useState(false);
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

  const navigation = (
    <nav aria-label="Main navigation" className="flex flex-col gap-1.5">
      {NAV.map(({ href, label, Icon }) => {
        const active = path === href || path?.startsWith(`${href}/`);
        return <Link key={href} href={href} onClick={() => setNavOpen(false)} aria-current={active ? "page" : undefined}
          className={cn("flex items-center gap-3 rounded-xl border border-transparent px-3 py-3 text-sm font-medium transition-colors",
            active ? "border-white/10 bg-white/10 text-white shadow-sm" : "text-slate-400 hover:bg-white/5 hover:text-white")}>
          <Icon aria-hidden className={cn("size-[18px]", active && "text-teal-400")} />
          {label}{active && <span aria-hidden className="ml-auto h-1.5 w-1.5 rounded-full bg-teal-400" />}
        </Link>;
      })}
    </nav>
  );
  const brand = <Link href="/run" onClick={() => setNavOpen(false)} className="flex items-center gap-3">
    <span className="flex size-10 items-center justify-center rounded-xl bg-[#0D9488] text-white"><Eye aria-hidden className="size-5" /></span>
    <span><span className="block text-2xl font-semibold tracking-tight md:text-3xl text-white">Nigraan <span className="ml-1 text-sm font-normal text-slate-400">نگران</span></span>
      <span className="block text-[10px] uppercase tracking-[0.16em] text-slate-400">Finance control tower</span></span>
  </Link>;

  return (
    <div className="flex min-h-screen">
      <a href="#main-content" className="fixed left-4 top-4 z-[60] -translate-y-24 rounded-lg bg-card px-4 py-2 shadow-lg focus:translate-y-0">Skip to content</a>
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-[#0B1422] px-5 py-7 lg:flex">
        {brand}
        <div className="mb-3 mt-10 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Workspace</div>
        {navigation}
        <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-slate-400">
          <div className="mb-3 flex items-center gap-2 font-medium text-slate-200"><ShieldCheck aria-hidden className="size-4 text-teal-400" />Decision intelligence</div>
          <div className="flex items-center gap-2"><Brain aria-hidden className="size-3.5" />Model {demo?.model_version ?? "Unavailable"}</div>
          <div className="mt-2">Document reader: {demo?.gemini ? "Gemini" : "PDF text + regex"}</div>
          <div className="mt-4 border-t border-white/10 pt-3 text-[11px]">Synthetic data · fictional company<br />AICON’26 demonstration</div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur">
          <div className="flex min-h-18 items-center gap-3 px-4 md:px-8">
            <Sheet open={navOpen} onOpenChange={setNavOpen}>
              <SheetTrigger asChild><Button size="icon" variant="outline" className="shrink-0 lg:hidden" aria-label="Open navigation"><Menu /></Button></SheetTrigger>
              <SheetContent className="max-w-xs bg-[#0B1422] p-6 text-white">
                <SheetTitle className="sr-only">Workspace navigation</SheetTitle>
                <SheetDescription className="sr-only">Navigate Nigraan’s finance workspace.</SheetDescription>
                <div className="mb-10 pr-8">{brand}</div>{navigation}
              </SheetContent>
            </Sheet>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">Bismillah Distributors <span className="hidden font-normal text-muted-foreground sm:inline">/ Lahore</span></div>
              <div className="mt-0.5 text-xs text-muted-foreground">Fictional company · {dayFull(demo?.as_of ?? null)}</div>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-3">
              <Popover.Root>
                <Popover.Trigger asChild>
                  <Button variant="ghost" className="h-auto gap-2 px-2 py-1.5" aria-label="Open user menu">
                    <span className="flex size-9 items-center justify-center rounded-full border border-border bg-muted text-xs font-semibold">{user.name.split(" ").slice(0, 2).map((n) => n[0]).join("")}</span>
                    <span className="hidden text-left sm:block"><span className="block text-xs font-semibold">{user.name}</span><span className="block text-[11px] text-muted-foreground">{ROLE_LABEL[user.role]}</span></span>
                    <ChevronDown className="size-3.5 text-muted-foreground" />
                  </Button>
                </Popover.Trigger>
                <Popover.Portal><Popover.Content align="end" sideOffset={8} className="z-50 w-64 rounded-xl border border-border bg-card p-4 shadow-lg">
                  <div className="text-sm font-semibold">{user.name}</div><div className="mt-1 break-all text-xs text-muted-foreground">{user.email}</div>
                  <div className="mt-3 rounded-lg bg-muted px-3 py-2 text-xs">Signed in as {ROLE_LABEL[user.role]}. Actions follow your role permissions.</div>
                  <Popover.Close className="mt-3 text-xs text-accent">Close menu</Popover.Close>
                </Popover.Content></Popover.Portal>
              </Popover.Root>
              <Tooltip content="Sign out"><Button size="icon" variant="ghost" onClick={logout} aria-label="Sign out"><LogOut /></Button></Tooltip>
            </div>
          </div>
          {demo?.demo_mode && (
            <div className="flex flex-wrap items-center gap-1 border-t border-border bg-muted/35 px-4 py-2 md:px-8">
              <span className="mr-2 rounded border border-border bg-card px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Demo controls</span>
              <Tooltip content="Restore the seeded company (history only, no open run)"><Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run("reset")}>
                {busy === "reset" ? <Loader2 className="animate-spin" /> : <RotateCcw />}Reset data
              </Button></Tooltip>
              <Tooltip content="Import this week's 40 invoices and score the payment run"><Button size="sm" variant="outline" disabled={!!busy || !!demo.open_run_id} onClick={() => run("week")}>
                {busy === "week" ? <Loader2 className="animate-spin" /> : <CalendarPlus />}Load demo week
              </Button></Tooltip>
              <Tooltip content="Retrain with recorded case outcomes; requires approver or owner"><span><Button size="sm" variant="ghost" disabled={!!busy || user.role === "accountant"} onClick={() => run("retrain")}>
                {busy === "retrain" ? <Loader2 className="animate-spin" /> : <Brain />}Retrain
              </Button></span></Tooltip>
              <span className="ml-auto hidden text-[11px] text-muted-foreground xl:block">Synthetic data · no real payments</span>
            </div>
          )}
        </header>
        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 outline-none md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}

export function PageTitle({ title, sub, children }: { title: string; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{title}</h1>
        {sub && <div className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{sub}</div>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
