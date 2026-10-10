"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Users } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { dateTime, day, rs } from "@/lib/format";
import { DecisionBadge } from "@/components/app/decision";
import { GraphView } from "@/components/app/graph-view";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, Skeleton, Stat } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type VR = {
  vendor: { id: number; name: string; ntn: string | null; category: string; phone: string; address: string; status: string; created_at: string; related_party_note: string | null };
  graph: { signal: number; links: { text: string; path: { id: string }[] }[]; neighbourhood: { nodes: { id: string; kind: string; label: string }[]; edges: { source: string; target: string }[] } };
  bank_history: { id: number; bank: string; last4: string; status: string; valid_from: string; valid_to: string | null; changed_by: string | null; approved_by: string | null; source: string; blocked: boolean }[];
  stats: { payments: number; median: number | null; total: number };
  recent_payments: { id: number; amount: number; status: string; created_at: string; invoice_no: string; score: number | null; decision: string | null }[];
};

export default function VendorPage() {
  const { id } = useParams<{ id: string }>();
  const { data: v, loading, error } = useApi<VR>(`/vendors/${id}/risk`);
  if (loading && !v) return <Skeleton className="h-96" />;
  if (error || !v) return <Empty icon={<Users />} title="Vendor not found">{error?.message}</Empty>;
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
          <CardHeader><CardTitle>Bank account history</CardTitle></CardHeader>
          <CardContent className="grid gap-2">
            {v.bank_history.map((b) => (
              <div key={b.id} className="rounded-md border border-border px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center gap-2 font-medium">{b.bank} ••{b.last4}<Badge variant="outline">{b.source.replace("_", " ")}</Badge>{b.status !== "active" && <Badge variant="review">{b.status}</Badge>}{b.blocked && <Badge variant="blocked">blocked</Badge>}</div>
                <div className="text-xs text-muted-foreground">{dateTime(b.valid_from)} → {b.valid_to ? dateTime(b.valid_to) : "current"} · by {b.changed_by ?? "—"} · approved by {b.approved_by ?? "nobody"}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <Card className="mt-5 animate-rise-in overflow-hidden [animation-delay:200ms]">
        <CardHeader><CardTitle>Recent payments</CardTitle></CardHeader>
        <Table>
          <THead><TR><TH>Invoice</TH><TH>Entered</TH><TH className="text-right">Amount</TH><TH>Status</TH><TH>Verdict</TH></TR></THead>
          <TBody>
            {v.recent_payments.map((p) => (
              <TR key={p.id}><TD className="font-mono text-xs">{p.invoice_no}</TD><TD className="text-xs">{dateTime(p.created_at)}</TD><TD className="tabular text-right">{rs(p.amount)}</TD><TD className="text-xs">{p.status}</TD><TD>{p.decision ? <DecisionBadge decision={p.decision} /> : <span className="text-xs text-muted-foreground">before Nigraan</span>}</TD></TR>
            ))}
          </TBody>
        </Table>
      </Card>
    </>
  );
}
