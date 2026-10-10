"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";
import {
  ChevronDown, Menu, PanelLeftClose, PanelLeftOpen, ShieldCheck, Brain, ClipboardList, Eye, FileUp, Flag, LayoutDashboard, Loader2, LogOut, Moon, RotateCcw, Settings2, ShieldAlert, Sun, Users, Wallet, CalendarPlus,
} from "lucide-react";
import { api, getActivity, subscribeActivity } from "@/lib/api";
import { ROLE_LABEL, useAuth } from "@/lib/auth";
import { forgetUnwatched, invalidateAll, prefetch, useApi, warm } from "@/lib/hooks";
import { changeTheme, openPreferences, usePrefs, useResolvedTheme } from "@/lib/preferences";
import type { RunDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import * as Popover from "@radix-ui/react-popover";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { dayFull } from "@/lib/format";

const RUN_PATH = "/payment-runs/current";

// `data` is the API path each screen opens with: hovering the link fetches it so the page renders instantly.
const NAV = [
  { href: "/run", label: "Payment run", Icon: ClipboardList, data: RUN_PATH },
  { href: "/flagged", label: "Flagged invoices", Icon: Flag, data: RUN_PATH },
  { href: "/cases", label: "Cases", Icon: ShieldAlert, data: "/cases?source=auto" },
  { href: "/upload", label: "Upload invoices", Icon: FileUp, data: "/demo/samples" },
  { href: "/cash", label: "Cash outlook", Icon: Wallet, data: "/cash/projection" },
  { href: "/dashboard", label: "Dashboard", Icon: LayoutDashboard, data: "/dashboard/summary" },
  { href: "/vendors", label: "Vendors", Icon: Users, data: "/vendors" },
];
const ITEM_H = 44; // h-11
const ITEM_GAP = 6; // gap-1.5

type DemoStatus = { demo_mode: boolean; open_run_id: number | null; model_version: string; gemini: boolean; as_of: string | null };

const SIDEBAR_KEY = "nigraan.sidebar-collapsed";
function sidebarSnapshot() {
  try { return window.localStorage.getItem(SIDEBAR_KEY) === "true"; } catch { return false; }
}
function subscribeSidebar(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("nigraan-sidebar", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("nigraan-sidebar", callback);
  };
}

/** Lines the approver still has to act on: locked red lines and yellow lines awaiting a second approval. */
export function flaggedOpen(run: RunDetail | null | undefined) {
  return run ? run.lines.filter((l) => l.status === "blocked" || (l.decision === "review" && l.status === "pending")).length : 0;
}

function centerOf(el: Element) {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const savedCollapsed = useSyncExternalStore(subscribeSidebar, sidebarSnapshot, () => false);
  const [collapseOverride, setCollapseOverride] = useState<boolean | null>(null);
  const collapsed = collapseOverride ?? savedCollapsed;
  const { data: demo } = useApi<DemoStatus>(user ? "/demo/status" : null);
  const { data: current } = useApi<{ run: RunDetail | null }>(user ? RUN_PATH : null);
  const [busy, setBusy] = useState<string | null>(null);
  const prefs = usePrefs();
  const theme = useResolvedTheme();
  const flagged = flaggedOpen(current?.run);

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);
  // Once the first screen is up, quietly load the other screens' data so every tab opens instantly.
  useEffect(() => {
    if (!user) return;
    const t = window.setTimeout(() => warm(["/dashboard/summary", "/cases?source=auto", "/cash/projection", "/vendors"]), 1500);
    return () => window.clearTimeout(t);
  }, [user]);

  if (!ready || !user) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 size-4 animate-spin" />Loading…</div>;
  }

  async function run(kind: "reset" | "week" | "retrain") {
    if (kind === "reset" && user?.role !== "owner") return;
    setBusy(kind);
    try {
      if (kind === "reset") {
        const r = await api.post<{ seconds: number }>("/demo/reset");
        forgetUnwatched();
        toast.success(`Demo data reset (${r.seconds}s). Seeded company restored.`);
        router.push("/run");
      } else if (kind === "week") {
        const r = await api.post<{ invoices: number; seconds: number; totals: Record<string, { count: number }> }>("/demo/load-week");
        forgetUnwatched();
        toast.success(`Loaded ${r.invoices} invoices and scored them in ${r.seconds}s: ${r.totals.blocked.count} blocked, ${r.totals.review.count} to review.`);
        router.push("/run");
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
        invalidateAll(); // the model version changed everywhere
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const activeIndex = NAV.findIndex(({ href }) => path === href || path?.startsWith(`${href}/`));
  function toggleSidebar() {
    const next = !collapsed;
    setCollapseOverride(next);
    try { window.localStorage.setItem(SIDEBAR_KEY, String(next)); } catch { /* Navigation works without storage. */ }
    window.dispatchEvent(new Event("nigraan-sidebar"));
  }
  const navigation = (compact = false) => (
    <nav aria-label="Main navigation" className="relative flex flex-col gap-1.5">
      {activeIndex >= 0 && (
        <span aria-hidden className="absolute inset-x-0 top-0 h-11 rounded-xl border border-white/10 bg-white/10 shadow-sm transition-transform duration-300 ease-[cubic-bezier(0.2,0.7,0.2,1)]"
          style={{ transform: `translateY(${activeIndex * (ITEM_H + ITEM_GAP)}px)` }} />
      )}
      {NAV.map((item, i) => (
        <NavLink key={item.href} {...item} compact={compact} active={i === activeIndex} count={item.href === "/flagged" ? flagged : 0} onNavigate={() => setNavOpen(false)} />
      ))}
    </nav>
  );
  const brand = <Link href="/run" onClick={() => setNavOpen(false)} className="group flex items-center gap-3">
    <span className="flex size-10 items-center justify-center rounded-xl bg-[#0D9488] text-white shadow-[0_0_0_4px_rgba(13,148,136,0.15)] transition-transform duration-300 group-hover:rotate-[-6deg] group-hover:scale-105"><Eye aria-hidden className="size-5" /></span>
    <span><span className="block text-2xl font-semibold tracking-tight md:text-3xl text-white">Nigraan <span className="ml-1 text-sm font-normal text-slate-400">نگران</span></span>
      <span className="block text-[10px] uppercase tracking-[0.16em] text-slate-400">Finance control tower</span></span>
  </Link>;

  return (
    <div className="flex min-h-screen">
      <TopProgress />
      <a href="#main-content" className="fixed left-4 top-4 z-[60] -translate-y-24 rounded-lg bg-card px-4 py-2 shadow-lg focus:translate-y-0">Skip to content</a>
      <aside id="desktop-navigation" data-collapsed={collapsed} aria-label="Workspace sidebar" className={cn("sidebar-panel sticky top-0 hidden h-screen shrink-0 flex-col overflow-x-hidden overflow-y-auto border-r border-white/5 bg-sidebar py-5 lg:flex", collapsed ? "w-20 px-3" : "w-64 px-5")}>
        <div className={cn("mb-5 flex", collapsed ? "justify-center" : "justify-end")}>
          <Tooltip content={collapsed ? "Expand sidebar" : "Minimize sidebar"}>
            <Button size="icon" variant="ghost" onClick={toggleSidebar} aria-label={collapsed ? "Expand sidebar" : "Minimize sidebar"} aria-expanded={!collapsed} aria-controls="desktop-navigation" className="size-9 text-slate-300 hover:bg-white/10 hover:text-white">
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>
          </Tooltip>
        </div>
        {collapsed ? <Link href="/run" aria-label="Nigraan home" className="mx-auto flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#0D9488] text-white"><Eye aria-hidden className="size-5" /></Link> : brand}
        <div aria-hidden className={cn("mb-3 mt-8 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500", collapsed && "invisible px-0")}>{collapsed ? "·" : "Workspace"}</div>
        {navigation(collapsed)}
        {collapsed ? <Tooltip content={`Synthetic demo · model ${demo?.model_version ?? "unavailable"}`}><div className="mx-auto mt-auto pt-6 text-slate-400" tabIndex={0} aria-label={`Synthetic demonstration. Model ${demo?.model_version ?? "unavailable"}`}><ShieldCheck aria-hidden className="size-5" /></div></Tooltip> : <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-slate-400">
          <div className="mb-3 flex items-center gap-2 font-medium text-slate-200"><ShieldCheck aria-hidden className="size-4 text-teal-400" />Decision intelligence</div>
          <div className="flex items-center gap-2"><Brain aria-hidden className="size-3.5" />Model {demo?.model_version ?? "Unavailable"}</div>
          <div className="mt-2">Document reader: {demo?.gemini ? "Gemini" : "PDF text / OCR + regex"}</div>
          <div className="mt-4 border-t border-white/10 pt-3 text-[11px]">Synthetic data · fictional company<br />AICON’26 demonstration</div>
        </div>}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-card/85 backdrop-blur-md">
          <div className="flex min-h-18 items-center gap-3 px-4 md:px-8">
            <Sheet open={navOpen} onOpenChange={setNavOpen}>
              <SheetTrigger asChild><Button size="icon" variant="outline" className="shrink-0 lg:hidden" aria-label="Open navigation"><Menu /></Button></SheetTrigger>
              <SheetContent side="left" className="max-w-xs border-white/10 bg-sidebar p-6 text-white">
                <SheetTitle className="sr-only">Workspace navigation</SheetTitle>
                <SheetDescription className="sr-only">Navigate Nigraan’s finance workspace.</SheetDescription>
                <div className="mb-10 pr-8">{brand}</div>{navigation()}
              </SheetContent>
            </Sheet>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">Bismillah Distributors <span className="hidden font-normal text-muted-foreground sm:inline">/ Lahore</span></div>
              <div className="mt-0.5 text-xs text-muted-foreground">Fictional company · {dayFull(demo?.as_of ?? null)}</div>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
              <Tooltip content={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
                <Button size="icon" variant="ghost" aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
                  onClick={(e) => changeTheme(theme === "dark" ? "light" : "dark", centerOf(e.currentTarget))} className="relative overflow-hidden">
                  <Sun className={cn("absolute transition-all duration-500", theme === "dark" ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-0 opacity-0")} />
                  <Moon className={cn("absolute transition-all duration-500", theme === "dark" ? "rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100")} />
                </Button>
              </Tooltip>
              <Popover.Root>
                <Popover.Trigger asChild>
                  <Button variant="ghost" className="h-auto gap-2 px-2 py-1.5" aria-label="Open user menu">
                    <span className="flex size-9 items-center justify-center rounded-full border border-border bg-muted text-xs font-semibold">{user.name.split(" ").slice(0, 2).map((n) => n[0]).join("")}</span>
                    <span className="hidden text-left sm:block"><span className="block text-xs font-semibold">{user.name}</span><span className="block text-[11px] text-muted-foreground">{ROLE_LABEL[user.role]}</span></span>
                    <ChevronDown className="size-3.5 text-muted-foreground" />
                  </Button>
                </Popover.Trigger>
                <Popover.Portal><Popover.Content align="end" sideOffset={8} className="z-50 w-64 origin-[var(--radix-popover-content-transform-origin)] rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-lift)] data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in">
                  <div className="text-sm font-semibold">{user.name}</div><div className="mt-1 break-all text-xs text-muted-foreground">{user.email}</div>
                  <div className="mt-3 rounded-lg bg-muted px-3 py-2 text-xs">Signed in as {ROLE_LABEL[user.role]}. Actions follow your role permissions.</div>
                  <Popover.Close asChild>
                    <button type="button" onClick={openPreferences} className="mt-3 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors hover:bg-muted">
                      <Settings2 aria-hidden className="size-4 text-muted-foreground" />{prefs.fabHidden ? "Show preferences button" : "Open preferences"}
                      {prefs.fabHidden && <kbd className="ml-auto rounded border border-border bg-muted px-1 text-[10px] text-muted-foreground">⇧P</kbd>}
                    </button>
                  </Popover.Close>
                  <Popover.Close className="mt-1 px-2 text-xs text-accent">Close menu</Popover.Close>
                </Popover.Content></Popover.Portal>
              </Popover.Root>
              <Tooltip content="Sign out"><Button size="icon" variant="ghost" onClick={logout} aria-label="Sign out"><LogOut /></Button></Tooltip>
            </div>
          </div>
          {demo?.demo_mode && (
            <div className="flex flex-wrap items-center gap-1 border-t border-border bg-muted/35 px-4 py-2 md:px-8">
              <span className="mr-2 rounded border border-border bg-card px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Demo controls</span>
              {user.role === "owner" ? <Tooltip content="Owner only: restore the seeded company (history only, no open run)"><Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run("reset")}>
                {busy === "reset" ? <Loader2 className="animate-spin" /> : <RotateCcw />}Reset data
              </Button></Tooltip> : <span className="mr-2 text-[11px] text-muted-foreground">Only the owner can reset data</span>}
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

function NavLink({ href, label, Icon, data, active, count, compact, onNavigate }: (typeof NAV)[number] & { active: boolean; count: number; compact: boolean; onNavigate: () => void }) {
  const countId = useId();
  const link = (
    <Link href={href} onClick={onNavigate} aria-label={label} aria-current={active ? "page" : undefined} aria-describedby={count ? countId : undefined}
      onMouseEnter={() => prefetch(data)} onFocus={() => prefetch(data)} onTouchStart={() => prefetch(data)}
      className={cn("group relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors duration-200", compact && "justify-center",
        active ? "text-white" : "text-slate-400 hover:bg-white/5 hover:text-white")}>
      <Icon aria-hidden className={cn("size-[18px] shrink-0 transition-transform duration-200 group-hover:scale-110", active && "text-teal-400")} />
      <span className={compact ? "sr-only" : "whitespace-nowrap"}>{label}</span>
      {count > 0 ? (
        <>
          <span key={count} aria-hidden className={cn("flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[11px] font-semibold text-white [animation:pop-badge_0.45s_var(--ease-spring)_backwards,soft-pulse_2.4s_ease-in-out_0.6s_infinite]", compact ? "absolute -right-1 -top-1 scale-90" : "ml-auto")}>{count}</span>
          <span id={countId} hidden>{count} need action</span>
        </>
      ) : active && !compact && <span aria-hidden className="ml-auto h-1.5 w-1.5 animate-pop-badge rounded-full bg-teal-400" />}
    </Link>
  );
  return compact ? <Tooltip content={label}>{link}</Tooltip> : link;
}

/** Thin bar at the top while the API is working (shown only if a request takes longer than ~200 ms). */
function TopProgress() {
  const busy = useSyncExternalStore(subscribeActivity, () => getActivity() > 0, () => false);
  return (
    <div aria-hidden className={cn("pointer-events-none fixed inset-x-0 top-0 z-[70] h-0.5 overflow-hidden transition-opacity", busy ? "opacity-100 delay-200 duration-200" : "opacity-0 duration-500")}>
      <div className="h-full w-full origin-left bg-gradient-to-r from-transparent via-teal-400 to-transparent [animation:progress-slide_1.1s_ease-in-out_infinite]" />
    </div>
  );
}

export function PageTitle({ title, sub, children }: { title: string; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
      <div className="animate-rise-in">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{title}</h1>
        {sub && <div className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{sub}</div>}
      </div>
      {children && <div className="flex animate-rise-in flex-wrap items-center gap-2 [animation-delay:80ms]">{children}</div>}
    </div>
  );
}
