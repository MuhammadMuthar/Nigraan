"use client";
import Link from "next/link";
import { useId, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Building2, CircleAlert, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { dateTime, day, rs } from "@/lib/format";
import { DecisionBadge } from "@/components/app/decision";
import { GraphView } from "@/components/app/graph-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Empty, Skeleton, Stat } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type VR = {
  vendor: { id: number; name: string; ntn: string | null; category: string; phone: string; address: string; status: string; created_at: string; related_party_note: string | null };
  graph: { signal: number; links: { text: string; path: { id: string }[] }[]; neighbourhood: { nodes: { id: string; kind: string; label: string }[]; edges: { source: string; target: string }[] } };
  bank_history: { id: number; bank: string; last4: string; status: string; valid_from: string; valid_to: string | null; changed_by: string | null; changed_by_id: number | null; approved_by: string | null; approved_by_id: number | null; source: string; blocked: boolean }[];
  stats: { payments: number; median: number | null; total: number };
  recent_payments: { id: number; amount: number; status: string; created_at: string; invoice_no: string; score: number | null; decision: string | null }[];
};

export default function VendorPage() {
  const { id } = useParams<{ id: string }>();
  const { data: v, loading, error, reload } = useApi<VR>(`/vendors/${id}/risk`);
  const { user } = useAuth();
  const [requesting, setRequesting] = useState(false);
  const [approving, setApproving] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const canApprove = user?.role === "approver" || user?.role === "owner";
  async function retry() {
    setRetrying(true);
    await reload();
    setRetrying(false);
  }
  async function approve(accountId: number) {
    setApproving(accountId);
    setActionError(null);
    try {
      await api.post(`/vendors/${id}/bank-changes/${accountId}/approve`);
      toast.success("Bank change approved by a second user");
      await reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setApproving(null);
    }
  }
  if (loading && !v) return <Skeleton className="h-96" />;
  if (error || !v) return <div role="alert"><Empty icon={<CircleAlert />} title={error?.status === 404 ? "Vendor not found" : "Could not load vendor"}><p>{error?.message}</p><Button className="mt-4" variant="outline" disabled={retrying} onClick={retry}>{retrying ? "Retrying…" : "Retry"}</Button></Empty></div>;
  const pending = v.bank_history.some((account) => account.status === "pending");
  return (
    <>
      <Link href="/vendors" className="group mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"><ArrowLeft className="size-4 transition-transform duration-200 group-hover:-translate-x-1" />Vendors</Link>
      <div className="mb-5 flex animate-rise-in flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">{v.vendor.name}</h1>
        {v.vendor.status === "blocked" && <Badge variant="blocked">Blocked</Badge>}
        <span className="text-sm text-muted-foreground">{v.vendor.category.replace("_", " ")} · NTN {v.vendor.ntn ?? "none"} · {v.vendor.phone} · since {day(v.vendor.created_at, { year: "numeric" })}</span>
      </div>
      <div className="stagger grid gap-4 sm:grid-cols-3">
        <Card><CardContent className="pt-5"><Stat label="Payments released" value={v.stats.payments} /></CardContent></Card>
        <Card><CardContent className="pt-5"><Stat label="Median payment" value={rs(v.stats.median)} /></CardContent></Card>
        <Card><CardContent className="pt-5"><Stat label="Relationship signal" value={v.graph.signal.toFixed(2)} sub={v.graph.links[0]?.text ?? "no shared identifiers"} tone={v.graph.signal >= 0.7 ? "blocked" : undefined} /></CardContent></Card>
      </div>
      <div className="stagger mt-5 grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Relationships</CardTitle></CardHeader>
          <CardContent>
            {v.vendor.related_party_note && <div className="mb-3 rounded-md bg-muted px-3 py-2 text-xs">{v.vendor.related_party_note}</div>}
            <GraphView nodes={v.graph.neighbourhood.nodes} edges={v.graph.neighbourhood.edges} path={(v.graph.links[0]?.path ?? []).map((p) => p.id)} height={300} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-wrap items-center justify-between gap-3"><CardTitle>Bank account history</CardTitle><Button size="sm" variant="outline" onClick={() => setRequesting(true)} disabled={pending}><Building2 />Request bank change</Button></CardHeader>
          <CardContent className="grid gap-2">
            <p className="mb-1 text-xs leading-relaxed text-muted-foreground">A requested account stays inactive until a different owner or approver approves it. Existing payment lines retain their recorded bank account.</p>
            {actionError && <p role="alert" className="rounded-lg border border-blocked/20 bg-blocked-soft p-3 text-sm text-blocked">{actionError}</p>}
            {v.bank_history.length === 0 && <p className="text-sm text-muted-foreground">No bank accounts recorded.</p>}
            {v.bank_history.map((b) => {
              const selfRequested = b.changed_by_id === user?.id;
              return <div key={b.id} className="rounded-xl border border-border px-3 py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2 font-medium">{b.bank} ••{b.last4}<Badge variant="outline">{b.source.replace("_", " ")}</Badge>{b.status === "pending" ? <Badge variant="review">Pending approval</Badge> : !b.valid_to && b.status === "active" ? <Badge variant="accent">Current account</Badge> : <Badge variant="outline">{b.status === "active" ? "Previous account" : b.status}</Badge>}{b.blocked && <Badge variant="blocked">Blocked</Badge>}</div>
                <div className="mt-1 text-xs leading-relaxed text-muted-foreground">{b.status === "pending" ? `Requested ${dateTime(b.valid_from)}` : `${dateTime(b.valid_from)} → ${b.valid_to ? dateTime(b.valid_to) : "current"}`} · by {b.changed_by ?? "—"} · approved by {b.approved_by ?? "not yet approved"}</div>
                {b.status === "pending" && <div className="mt-3 border-t border-border pt-3">
                  {canApprove && b.changed_by_id != null && !selfRequested ? <Button size="sm" disabled={approving !== null} onClick={() => approve(b.id)}>{approving === b.id ? <Loader2 className="animate-spin" /> : <ShieldCheck />}Approve bank change</Button>
                    : <p className="text-xs text-muted-foreground">{selfRequested ? "You requested this change. A different owner or approver must approve it." : "An owner or approver who did not request this change must approve it."}</p>}
                </div>}
              </div>;
            })}
          </CardContent>
        </Card>
      </div>
      <Card className="mt-5 animate-rise-in overflow-hidden [animation-delay:200ms]">
        <CardHeader><CardTitle>Recent payments</CardTitle></CardHeader>
        <Table>
          <THead><TR><TH>Invoice</TH><TH>Entered</TH><TH className="text-right">Amount</TH><TH>Status</TH><TH>Verdict</TH></TR></THead>
          <TBody>
            {v.recent_payments.length === 0 && <TR><TD colSpan={5} className="py-8 text-center text-muted-foreground">No payments recorded for this vendor.</TD></TR>}
            {v.recent_payments.map((p) => (
              <TR key={p.id}><TD className="font-mono text-xs">{p.invoice_no}</TD><TD className="text-xs">{dateTime(p.created_at)}</TD><TD className="tabular text-right">{rs(p.amount)}</TD><TD className="text-xs">{p.status}</TD><TD>{p.decision ? <DecisionBadge decision={p.decision} /> : <span className="text-xs text-muted-foreground">before Nigraan</span>}</TD></TR>
            ))}
          </TBody>
        </Table>
      </Card>
      <BankChangeDialog open={requesting} onOpenChange={setRequesting} vendorId={id} onSaved={reload} />
    </>
  );
}

function BankChangeDialog({ open, onOpenChange, vendorId, onSaved }: { open: boolean; onOpenChange: (open: boolean) => void; vendorId: string; onSaved: () => Promise<void> }) {
  const prefix = useId();
  const [iban, setIban] = useState("");
  const [bank, setBank] = useState("");
  const [source, setSource] = useState("vendor_letter");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/vendors/${vendorId}`, { iban: iban.replace(/\s/g, "").toUpperCase(), bank_name: bank.trim(), change_source: source });
      toast.success("Bank change requested; independent approval required");
      onOpenChange(false);
      setIban("");
      setBank("");
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
    <DialogContent>
      <DialogTitle>Request bank change</DialogTitle>
      <DialogDescription>Verify these details with the vendor through a known contact. This request does not activate the account.</DialogDescription>
      <form onSubmit={submit} className="mt-5 grid gap-4">
        <div className="grid gap-1.5"><Label htmlFor={`${prefix}-bank`}>New bank name</Label><Input id={`${prefix}-bank`} value={bank} onChange={(e) => setBank(e.target.value)} required disabled={busy} /></div>
        <div className="grid gap-1.5"><Label htmlFor={`${prefix}-iban`}>New Pakistan IBAN</Label><Input id={`${prefix}-iban`} value={iban} onChange={(e) => setIban(e.target.value)} className="font-mono uppercase" autoComplete="off" spellCheck={false} required disabled={busy} /></div>
        <div className="grid gap-1.5"><Label htmlFor={`${prefix}-source`}>Request received through</Label><select id={`${prefix}-source`} value={source} onChange={(e) => setSource(e.target.value)} disabled={busy} className="h-10 w-full rounded-md border border-border bg-card px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><option value="vendor_letter">Vendor letter</option><option value="email">Email</option><option value="phone">Phone</option><option value="portal">Vendor portal</option></select></div>
        <p className="text-xs leading-relaxed text-muted-foreground">Email and phone requests remain risk signals. Independent approval does not replace verification.</p>
        {error && <p role="alert" className="rounded-lg border border-blocked/20 bg-blocked-soft p-3 text-sm text-blocked">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4"><Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />}Submit bank change</Button></div>
      </form>
    </DialogContent>
  </Dialog>;
}
