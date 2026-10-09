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
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-[#0b3b37] p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-md bg-white/10"><Eye className="size-5" /></div>
          <div className="text-lg font-bold tracking-tight">Nigraan <span className="font-normal text-white/60">نگران</span></div>
        </div>
        <div className="max-w-lg">
          <h1 className="text-3xl font-semibold leading-tight">Checks every rupee going out, and tells you whether what&apos;s coming in will cover it.</h1>
          <p className="mt-4 text-white/70">A finance control tower for Pakistani SMEs. Before the weekly payment run, every line gets a verdict with reasons, and you see whether cash stays above your reserve.</p>
          <div className="mt-8 grid gap-4 text-sm">
            <div className="flex gap-3"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-emerald-300" /><div><b>Fraud firewall.</b> Duplicate detector, risk model, anomaly detector and relationship graph score every payment. Red lines cannot be released.</div></div>
            <div className="flex gap-3"><Wallet className="mt-0.5 size-5 shrink-0 text-emerald-300" /><div><b>13-week cash.</b> Late-payment model on receivables plus a deterministic cash engine that catches mid-week reserve breaches.</div></div>
          </div>
        </div>
        <div className="text-xs text-white/50">AICON&apos;26 Build With AI · Financial Operations · 100% synthetic data, fictional company</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h2 className="text-xl font-semibold">Sign in</h2>
          <p className="mt-1 text-sm text-muted-foreground">Bismillah Distributors (fictional), Lahore</p>
          {demoUsers.length > 0 && (
            <div className="mt-6">
              <Label>Demo users (password: <span className="font-mono">nigraan-demo</span>)</Label>
              <div className="mt-2 grid gap-2">
                {demoUsers.map((u) => (
                  <button key={u.id} type="button" disabled={busy}
                    onClick={() => { setEmail(u.email); setPassword("nigraan-demo"); submit(undefined, u.email, "nigraan-demo"); }}
                    className="group flex items-center justify-between rounded-md border border-border bg-card px-3 py-2.5 text-left transition-colors hover:border-accent hover:bg-accent-soft/50">
                    <div>
                      <div className="text-sm font-medium">{u.name} <span className="text-xs font-normal text-muted-foreground">· {ROLE_LABEL[u.role]}</span></div>
                      <div className="text-xs text-muted-foreground">{ROLE_HELP[u.role]}</div>
                    </div>
                    <ArrowRight className="size-4 text-muted-foreground group-hover:text-accent" />
                  </button>
                ))}
              </div>
              <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground"><div className="h-px flex-1 bg-border" />or<div className="h-px flex-1 bg-border" /></div>
            </div>
          )}
          <form onSubmit={submit} className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></div>
            <div className="grid gap-1.5"><Label htmlFor="pw">Password</Label><Input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div>
            {err && <div className="rounded-md bg-blocked-soft px-3 py-2 text-sm text-blocked">{err}</div>}
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />}Sign in</Button>
          </form>
        </div>
      </div>
    </div>
  );
}
