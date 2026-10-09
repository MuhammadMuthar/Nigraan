"use client";
import Link from "next/link";
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { dateTime, rs } from "@/lib/format";
import { PageTitle } from "@/components/app/shell";
import { FRAUD_NAMES, ScoreBar } from "@/components/app/decision";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Empty, Skeleton } from "@/components/ui/misc";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type CaseRow = {
  id: number; status: string; fraud_type: string | null; source: string; opened_at: string; resolved_at: string | null;
  resolved_by: string | null; amount: number; vendor: string; invoice_no: string; score: number | null; top_reason: string | null;
};

const STATUS: Record<string, { label: string; variant: "blocked" | "allow" | "default" }> = {
  open: { label: "Open", variant: "blocked" }, confirmed_fraud: { label: "Confirmed fraud", variant: "default" }, false_alarm: { label: "False alarm", variant: "allow" },
};

export default function CasesPage() {
  const [tab, setTab] = useState("auto");
  const path = tab === "auto" ? "/cases?source=auto" : tab === "open" ? "/cases?status=open" : "/cases?source=historical";
  const { data, loading } = useApi<CaseRow[]>(path);
  return (
    <>
      <PageTitle title="Cases" sub="Every red line opens a case automatically. Outcomes become training labels for the next retrain." />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="auto">Opened by Nigraan</TabsTrigger>
          <TabsTrigger value="open">Open only</TabsTrigger>
          <TabsTrigger value="historical">Historical audit (pre-Nigraan)</TabsTrigger>
        </TabsList>
      </Tabs>
      <Card className="mt-4">
        {loading && !data ? <div className="p-4"><Skeleton className="h-40" /></div> : !data || data.length === 0 ? (
          <div className="p-4"><Empty icon={<ShieldAlert />} title="No cases here">Load the demo week to see Nigraan open cases for blocked lines.</Empty></div>
        ) : (
          <Table>
            <THead><TR><TH>Case</TH><TH>Status</TH><TH>Score</TH><TH>Vendor</TH><TH>Suspected pattern</TH><TH className="text-right">Amount</TH><TH>Top reason</TH><TH>Opened</TH></TR></THead>
            <TBody>
              {data.map((c) => (
                <TR key={c.id} className="hover:bg-muted/50">
                  <TD><Link href={`/cases/${c.id}`} className="font-medium text-accent hover:underline">#{c.id}</Link></TD>
                  <TD><Badge variant={STATUS[c.status]?.variant}>{STATUS[c.status]?.label ?? c.status}</Badge></TD>
                  <TD><ScoreBar score={c.score} /></TD>
                  <TD><Link href={`/cases/${c.id}`} className="font-medium hover:underline">{c.vendor}</Link><div className="text-xs text-muted-foreground">{c.invoice_no}</div></TD>
                  <TD className="text-sm">{c.fraud_type ? FRAUD_NAMES[c.fraud_type] : "—"}</TD>
                  <TD className="tabular text-right">{rs(c.amount)}</TD>
                  <TD className="max-w-[340px] text-sm text-muted-foreground"><div className="line-clamp-2">{c.top_reason ?? (c.source === "historical" ? "Found in internal audit before Nigraan" : "—")}</div></TD>
                  <TD className="text-xs text-muted-foreground">{dateTime(c.opened_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
