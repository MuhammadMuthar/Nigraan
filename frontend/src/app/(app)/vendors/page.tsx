"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Search, Users } from "lucide-react";
import { prefetch, useApi } from "@/lib/hooks";
import { day, rs } from "@/lib/format";
import { PageTitle } from "@/components/app/shell";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Empty, Skeleton } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type V = { id: number; name: string; category: string; ntn: string | null; status: string; bank: string | null; last_bank_change: string | null; paid_total: number; open_cases: number; related_party_note: string | null; pending_bank_change: boolean };

export default function VendorsPage() {
  const router = useRouter();
  const { data, loading } = useApi<V[]>("/vendors");
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((v) => v.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageTitle title="Vendors" sub="Vendor master with bank-change history. A bank change needs a second user before it is used.">
        <div className="relative"><Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search vendors" placeholder="Search vendors" value={q} onChange={(e) => setQ(e.target.value)} className="w-56 pl-9" /></div>
      </PageTitle>
      <Card className="animate-rise-in overflow-hidden [animation-delay:80ms]">
        {loading && !data ? <div className="p-4"><Skeleton className="h-60" /></div> : rows.length === 0 ? <div className="p-4"><Empty icon={<Users />} title="No vendors" /></div> : (
          <Table>
            <THead><TR><TH>Vendor</TH><TH>Category</TH><TH>NTN</TH><TH>Bank</TH><TH>Last bank change</TH><TH className="text-right">Paid (12 months)</TH><TH>Flags</TH></TR></THead>
            <TBody>
              {rows.map((v, i) => (
                <TR key={v.id} className="row-in cursor-pointer hover:bg-muted/50" style={{ "--i": i } as React.CSSProperties} onMouseEnter={() => prefetch(`/vendors/${v.id}/risk`)} onClick={() => router.push(`/vendors/${v.id}`)}>
                  <TD><Link href={`/vendors/${v.id}`} className="font-medium hover:underline">{v.name}</Link></TD>
                  <TD className="text-xs capitalize">{v.category.replace("_", " ")}</TD>
                  <TD className="font-mono text-xs">{v.ntn ?? <span className="text-muted-foreground">none</span>}</TD>
                  <TD className="text-xs">{v.bank}</TD>
                  <TD className="text-xs">{v.last_bank_change ? day(v.last_bank_change, { year: "numeric" }) : "—"}</TD>
                  <TD className="tabular text-right">{rs(v.paid_total)}</TD>
                  <TD className="flex flex-wrap gap-1">
                    {v.status === "blocked" && <Badge variant="blocked">Blocked</Badge>}
                    {v.open_cases > 0 && <Badge variant="blocked">{v.open_cases} open case(s)</Badge>}
                    {v.related_party_note && <Badge variant="outline">Related party</Badge>}
                    {v.pending_bank_change && <Badge variant="review">Bank change pending</Badge>}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
