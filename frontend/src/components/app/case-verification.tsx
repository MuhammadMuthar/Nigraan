"use client";

import { useState } from "react";
import { Languages, Phone, ShieldCheck } from "lucide-react";
import { dateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export type VerificationPlan = {
  checklist: { id: string; label: string }[];
  registered_phone: string | null;
  phone_history_available: boolean;
  bank_accounts: { id: number; bank_name: string; last4: string; status: string; valid_from: string; valid_to: string | null; change_source: string; requested_by: string | null; approved_by: string | null }[];
  requester: string | null;
  call_script: { en: string; ur: string };
  recorded_result: null | { result: string; method: string; checks: string[]; reference: string; by: string | null; at: string; note?: string | null };
};

const METHODS: Record<string, string> = {
  registered_phone: "Callback to registered phone", documents: "Supporting documents", in_person: "In-person verification", requester_review: "Internal records review",
};

export function CaseVerification({ plan, suggestion, finding }: { plan: VerificationPlan | undefined; suggestion: string; finding?: string | null }) {
  const [lang, setLang] = useState<"en" | "ur">("en");
  const recorded = plan?.recorded_result;
  return (
    <Card className="border-accent/25">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4 text-accent" />Suggested verification</CardTitle>
        <CardDescription>Use source records and an independent check. Record the result before closing the case.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm leading-relaxed">
        <p>{suggestion}</p>
        {plan ? (
          <>
            <dl className="grid gap-3 rounded-lg bg-muted/40 p-3 sm:grid-cols-2">
              <div><dt className="text-xs text-muted-foreground">Current registered phone</dt><dd className="mt-1 flex items-center gap-1.5 font-medium"><Phone className="size-3.5 text-muted-foreground" />{plan.registered_phone || "Not recorded"}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Payment requester</dt><dd className="mt-1 font-medium">{plan.requester || "Not recorded"}</dd></div>
              {!plan.phone_history_available && <div className="text-xs text-muted-foreground sm:col-span-2">The phone is from the current vendor record. A trusted historical phone has not been independently established.</div>}
            </dl>
            {plan.bank_accounts.length > 0 && (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-left text-xs">
                  <caption className="border-b border-border bg-muted/30 px-3 py-2 text-left font-semibold text-foreground">Registered bank records · masked accounts</caption>
                  <thead><tr className="border-b border-border text-muted-foreground"><th scope="col" className="px-3 py-2 font-medium">Bank / account</th><th scope="col" className="px-3 py-2 font-medium">Record</th><th scope="col" className="px-3 py-2 font-medium">Change / approval</th></tr></thead>
                  <tbody>{[...plan.bank_accounts].sort((a, b) => a.valid_from.localeCompare(b.valid_from)).map((bank) => (
                    <tr key={bank.id} className="border-b border-border last:border-0">
                      <th scope="row" className="px-3 py-2 font-medium">{bank.bank_name} ••{bank.last4}</th>
                      <td className="px-3 py-2"><span>{bank.valid_to ? "Earlier record" : "Current record"} · {bank.status.replaceAll("_", " ")}</span><div className="text-muted-foreground">{dateTime(bank.valid_from)}{bank.valid_to && <> to {dateTime(bank.valid_to)}</>}</div></td>
                      <td className="px-3 py-2">{bank.requested_by || "Requester not recorded"}<div className="text-muted-foreground">{bank.change_source.replaceAll("_", " ")} · approved by {bank.approved_by || "no approval recorded"}</div></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            <div>
              <h3 className="mb-2 text-sm font-semibold">Checks required for the outcome</h3>
              <ol className="grid list-decimal gap-1.5 pl-5 text-muted-foreground">{plan.checklist.map((item) => <li key={item.id}>{item.label}</li>)}</ol>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">Vendor callback script</h3>
                <Button size="sm" variant="ghost" aria-label={`Call script in ${lang === "en" ? "Roman Urdu" : "English"}`} onClick={() => setLang(lang === "en" ? "ur" : "en")}><Languages />{lang === "en" ? "Roman Urdu" : "English"}</Button>
              </div>
              <p aria-live="polite" className="whitespace-pre-line text-sm">{plan.call_script[lang]}</p>
              <p className="mt-2 text-xs text-muted-foreground">Verification prompt built from the case records; this is separate from the AI-generated explanation.</p>
            </div>
            {recorded && (
              <section aria-label="Recorded verification" className="rounded-lg border border-accent/25 bg-accent-soft p-3">
                <Badge variant="outline">Verification recorded</Badge>
                <p className="mt-2 font-semibold">{recorded.result === "verified_legitimate" ? "Legitimate payment verified" : "Issue confirmed"}</p>
                <p className="mt-1 text-xs text-muted-foreground">{METHODS[recorded.method] || recorded.method} · {recorded.by || "Name not recorded"} · {dateTime(recorded.at)}</p>
                <p className="mt-2 whitespace-pre-line text-sm"><span className="font-medium">Evidence reference: </span>{recorded.reference}</p>
                {(recorded.note || finding) && <p className="mt-2 whitespace-pre-line text-sm"><span className="font-medium">Finding: </span>{recorded.note || finding}</p>}
              </section>
            )}
          </>
        ) : <p className="text-xs text-muted-foreground">Detailed verification requirements are unavailable. Reload the case before recording an outcome.</p>}
      </CardContent>
    </Card>
  );
}
