"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, Eye, Loader2, ShieldCheck, Wallet } from "lucide-react";
import { api, type User } from "@/lib/api";
import { ROLE_LABEL, useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";

const ROLE_HELP: Record<string, string> = {
  accountant: "Enters invoices, prepares the run",
  approver: "Second approver for yellow lines",
  owner: "Releases payments above the limit, resolves cases",
};

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoUsers, setDemoUsers] = useState<User[]>([]);

  useEffect(() => {
    if (user) router.replace("/run");
  }, [user, router]);
  useEffect(() => {
    api.get<User[]>("/auth/demo-users").then(setDemoUsers).catch((e) => setErr(e.message));
  }, []);

  async function submit(e?: React.FormEvent, em = email, pw = password) {
    e?.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(em, pw);
      router.replace("/run");
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-[#0B1422] p-12 text-white lg:flex xl:p-16" aria-label="About Nigraan">
        <span aria-hidden className="pointer-events-none absolute -right-24 top-1/3 size-96 rounded-full bg-teal-500/10 blur-3xl motion-safe:animate-pulse" />
        <div className="flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-[#0D9488]"><Eye aria-hidden className="size-6" /></div>
          <div className="text-2xl font-semibold tracking-tight">Nigraan <span className="ml-1 text-lg font-normal text-slate-400">نگران</span></div>
        </div>
        <div className="stagger max-w-lg py-12">
          <div className="mb-6 text-xs font-medium uppercase tracking-[0.2em] text-teal-300">Finance control tower / Pakistan</div>
          <h1 className="text-4xl font-semibold leading-[1.15] tracking-tight xl:text-5xl">Every rupee.<br />A clearer decision.</h1>
          <p className="mt-6 max-w-md text-base leading-relaxed text-slate-300">Check what goes out. See whether what comes in will cover it. Bring payment risk and cash visibility into one workspace.</p>
          <div className="mt-10 grid gap-5 border-t border-white/10 pt-8">
            <div className="flex gap-4"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5"><ShieldCheck aria-hidden className="size-5 text-teal-300" /></span><div><h2 className="text-sm font-semibold">Investigate before you pay</h2><p className="mt-1 text-sm leading-relaxed text-slate-400">Invoice, bank and relationship evidence behind every risk verdict. Blocked lines stay locked.</p></div></div>
            <div className="flex gap-4"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5"><Wallet aria-hidden className="size-5 text-teal-300" /></span><div><h2 className="text-sm font-semibold">Look 13 weeks ahead</h2><p className="mt-1 text-sm leading-relaxed text-slate-400">Understand the reserve impact with facts, estimates and assumptions clearly separated.</p></div></div>
          </div>
        </div>
        <div className="flex flex-wrap justify-between gap-2 border-t border-white/10 pt-5 text-xs text-slate-400"><span>AICON’26 · Financial Operations</span><span>Synthetic data only</span></div>
      </section>
      <main className="flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-md animate-rise-in">
          <div className="mb-8 flex items-center gap-2 text-lg font-semibold lg:hidden"><span className="flex size-9 items-center justify-center rounded-xl bg-[#0D9488] text-white"><Eye className="size-5" /></span>Nigraan <span className="text-muted-foreground">نگران</span></div>
          <div className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-accent">Welcome to your workspace</div>
          <h2 className="text-3xl font-semibold tracking-tight">Sign in to Nigraan</h2>
          <p className="mt-2 text-sm text-muted-foreground">Bismillah Distributors · Lahore<br /><span className="text-xs">Fictional company · 100% synthetic demo data</span></p>
          {demoUsers.length > 0 && (
            <section className="mt-7" aria-labelledby="demo-heading">
              <div className="mb-3 flex items-center justify-between"><h3 id="demo-heading" className="text-sm font-semibold">Choose a demo role</h3><span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">One-click access</span></div>
              <div className="stagger grid gap-2.5">
                {demoUsers.map((u) => (
                  <button key={u.id} type="button" disabled={busy}
                    onClick={() => { setEmail(u.email); setPassword("nigraan-demo"); submit(undefined, u.email, "nigraan-demo"); }}
                    className="lift group flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-left shadow-[var(--shadow-card)] hover:border-accent/50 hover:bg-accent-soft/40 disabled:opacity-50">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground transition-colors group-hover:bg-accent-soft group-hover:text-accent">{u.name.split(" ").slice(0, 2).map((n) => n[0]).join("")}</span>
                    <span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{u.name} <span className="text-xs font-normal text-muted-foreground">· {ROLE_LABEL[u.role]}</span></span><span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{ROLE_HELP[u.role]}</span></span>
                    <ArrowRight aria-hidden className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-accent" />
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs text-muted-foreground">Demo password: <span className="font-mono">nigraan-demo</span>. Each role keeps its own permissions.</p>
              <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground"><div className="h-px flex-1 bg-border" />or use your credentials<div className="h-px flex-1 bg-border" /></div>
            </section>
          )}
          <form onSubmit={submit} className="grid gap-4" aria-busy={busy}>
            <div className="grid gap-1.5"><Label htmlFor="email">Email address</Label><Input id="email" type="email" placeholder="you@company.pk" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
            <div className="grid gap-1.5"><Label htmlFor="pw">Password</Label><Input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
            {err && <div role="alert" className="rounded-xl border border-blocked/20 bg-blocked-soft px-3 py-2 text-sm text-blocked">{err}</div>}
            <Button className="h-11" type="submit" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <ArrowRight />} {busy ? "Signing in…" : "Sign in"}</Button>
          </form>
        </div>
      </main>
    </div>
  );
}
