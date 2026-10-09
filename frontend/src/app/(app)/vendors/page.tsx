"use client";
import Link from "next/link";
import { useState } from "react";
import { Users } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { day, rs } from "@/lib/format";
import { PageTitle } from "@/components/app/shell";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Empty, Skeleton } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

type V = { id: number; name: string; category: string; ntn: string | null; status: string; bank: string | null; last_bank_change: string | null; paid_total: number; open_cases: number; related_party_note: string | null; pending_bank_change: boolean };

export default function VendorsPage() {
  const { data, loading } = useApi<V[]>("/vendors");
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((v) => v.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <PageTitle title="Vendors" sub="Vendor master with bank-change history. A bank change needs a second user before it is used.">
        <Input placeholder="Search vendors" value={q} onChange={(e) => setQ(e.target.value)} className="w-56" />
      </PageTitle>
      <Card>
        {loading && !data ? <div className="p-4"><Skeleton className="h-60" /></div> : rows.length === 0 ? <div className="p-4"><Empty icon={<Users />} title="No vendors" /></div> : (
          <Table>
            <THead><TR><TH>Vendor</TH><TH>Category</TH><TH>NTN</TH><TH>Bank</TH><TH>Last bank change</TH><TH className="text-right">Paid (12 months)</TH><TH>Flags</TH></TR></THead>
            <TBody>
              {rows.map((v) => (
                <TR key={v.id} className="hover:bg-muted/50">
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
