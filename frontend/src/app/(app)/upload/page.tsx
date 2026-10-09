"use client";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, CircleAlert, CircleCheck, FileText, FileUp, Loader2, ScanText, TriangleAlert } from "lucide-react";
import { api, API_URL, getToken } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Reason, TraceStep } from "@/lib/types";
import { PageTitle } from "@/components/app/shell";
import { DecisionBadge } from "@/components/app/decision";
import { AgentTrace } from "@/components/app/trace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Extracted = {
  invoice_id: number; status: string; ready_to_score: boolean; engine: string; cached: boolean;
  fields: Record<string, unknown> & { line_items?: { name: string; qty: number | null; unit_price: number | null; amount: number | null }[] };
  confidence: Record<string, number>; low_confidence: string[]; checks: { check: string; ok: boolean; text: string }[]; flags: string[];
  vendor: { id: number; name: string; method: string; confidence: number } | null; trace: TraceStep[];
};
type Scored = { payment_id: number; score: number; decision: string; reasons: Reason[]; trace: TraceStep[]; case_id: number | null };
type Item = { key: string; name: string; state: "uploading" | "extracted" | "scoring" | "scored" | "error"; ext?: Extracted; score?: Scored; error?: string };
type Sample = { name: string; group: string; hint: string };

const FIELD_LABEL: Record<string, string> = {
  vendor_name: "Vendor", ntn: "NTN", strn: "STRN", invoice_no: "Invoice no.", invoice_date: "Invoice date", due_date: "Due date",
  subtotal: "Subtotal (Rs)", tax: "Sales tax (Rs)", total: "Total (Rs)", iban: "IBAN",
};
const ENGINE_LABEL: Record<string, string> = {
  gemini: "Gemini vision", gemini_cached: "Gemini (cached replay)", pdf_text_regex: "PDF text + regex", ocr_regex: "Tesseract OCR + regex", cached: "Cached extraction",
};

export default function UploadPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { data: samples } = useApi<Sample[]>("/demo/samples");

  const update = (key: string, patch: Partial<Item>) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...patch } : x)));

  const score = useCallback(async (key: string, invoiceId: number) => {
    update(key, { state: "scoring" });
    try {
      const s = await api.post<Scored>(`/invoices/${invoiceId}/score`);
      update(key, { state: "scored", score: s });
    } catch (e) {
      update(key, { state: "error", error: (e as Error).message });
    }
  }, []);

  const handle = useCallback(async (file: File) => {
    const key = `${file.name}-${Date.now()}-${Math.random()}`;
    setItems((xs) => [{ key, name: file.name, state: "uploading" }, ...xs]);
    const form = new FormData();
    form.append("file", file);
    try {
      const ext = await api.upload<Extracted>("/invoices/upload", form);
      update(key, { state: "extracted", ext });
      if (ext.ready_to_score) await score(key, ext.invoice_id);
    } catch (e) {
      update(key, { state: "error", error: (e as Error).message });
    }
  }, [score]);

  async function loadSample(s: Sample) {
    try {
      const res = await fetch(`${API_URL}/api/v1/demo/samples/${s.group}/${encodeURIComponent(s.name)}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      const blob = await res.blob();
      await handle(new File([blob], s.name, { type: "application/pdf" }));
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <>
      <PageTitle title="Upload invoices" sub="The document reader extracts fields into a strict schema; deterministic checks set the confidence. The LLM never decides." />
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); Array.from(e.dataTransfer.files).forEach(handle); }}
        onClick={() => input.current?.click()}
        className={cn("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed bg-card px-6 py-10 text-center transition-colors",
          drag ? "border-accent bg-accent-soft" : "border-border hover:border-accent/50")}
      >
        <FileUp className="size-8 text-accent" />
        <div className="text-sm font-semibold">Drop invoice PDFs or images here</div>
        <div className="text-xs text-muted-foreground">or click to choose · PDF, PNG, JPG up to 8 MB</div>
        <input ref={input} type="file" accept=".pdf,image/*" multiple hidden onChange={(e) => Array.from(e.target.files ?? []).forEach(handle)} />
      </div>
      {samples && samples.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">No files handy? Try a sample:</span>
          {samples.map((s) => (
            <Button key={s.group + s.name} size="sm" variant="outline" onClick={() => loadSample(s)} title={s.name}>
              <FileText />{s.hint}: {s.name.replace(/^resent_|^new_/, "").slice(0, 26)}
            </Button>
          ))}
        </div>
      )}
      <div className="mt-6 grid gap-4">
        {items.map((it) => <UploadCard key={it.key} it={it} onRescore={score} onUpdate={(p) => update(it.key, p)} />)}
      </div>
    </>
  );
}

function UploadCard({ it, onRescore, onUpdate }: { it: Item; onRescore: (key: string, id: number) => void; onUpdate: (p: Partial<Item>) => void }) {
  const ext = it.ext;
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  async function confirm() {
    if (!ext) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = { confirm: true };
      for (const [k, v] of Object.entries(edits)) {
        if (["subtotal", "tax", "total"].includes(k)) body[k] = Number(v.replace(/,/g, ""));
        else if (["invoice_no", "invoice_date", "due_date"].includes(k)) body[k] = v;
      }
      await api.patch(`/invoices/${ext.invoice_id}`, body);
      onUpdate({ ext: { ...ext, status: "received" } });
      onRescore(it.key, ext.invoice_id);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <FileText className="size-4 text-muted-foreground" />
        <div className="min-w-0 flex-1 truncate text-sm font-medium">{it.name}</div>
        {ext && <Badge variant={ext.cached ? "default" : "accent"}><ScanText className="size-3.5" />{ENGINE_LABEL[ext.engine] ?? ext.engine}{ext.cached ? " · cached" : ""}</Badge>}
        {it.state === "uploading" && <Badge variant="outline"><Loader2 className="size-3.5 animate-spin" />Reading document…</Badge>}
        {it.state === "scoring" && <Badge variant="outline"><Loader2 className="size-3.5 animate-spin" />Scoring…</Badge>}
        {it.score && <DecisionBadge decision={it.score.decision} large />}
        {it.score && <span className="tabular text-sm font-semibold">{it.score.score}/100</span>}
      </div>
      {it.state === "error" && <div className="flex items-center gap-2 px-4 py-3 text-sm text-blocked"><CircleAlert className="size-4" />{it.error}</div>}
      {ext && (
        <div className="grid gap-5 p-4 lg:grid-cols-[1.2fr_1fr]">
          <div>
            <div className="grid gap-1">
              {Object.keys(FIELD_LABEL).map((f, i) => {
                const v = ext.fields[f];
                const c = ext.confidence[f] ?? 0;
                const low = c < 0.8;
                const editable = low && ext.status === "draft" && ["invoice_no", "invoice_date", "due_date", "subtotal", "tax", "total"].includes(f);
                return (
                  <div key={f} className={cn("fill-in grid grid-cols-[110px_1fr_70px] items-center gap-2 rounded px-2 py-1 text-sm", low && "bg-review-soft")} style={{ animationDelay: `${i * 60}ms` }}>
                    <div className="text-xs text-muted-foreground">{FIELD_LABEL[f]}</div>
                    {editable ? (
                      <Input className="h-7 text-sm" defaultValue={v == null ? "" : String(v)} onChange={(e) => setEdits((x) => ({ ...x, [f]: e.target.value }))} />
                    ) : (
                      <div className={cn("truncate font-mono text-[13px]", v == null && "text-muted-foreground")}>{v == null ? "not found" : typeof v === "number" ? v.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : String(v)}</div>
                    )}
                    <div className="flex items-center gap-1">
                      <div className="h-1.5 w-8 overflow-hidden rounded-full bg-muted"><div className={cn("h-full", low ? "bg-review" : "bg-allow")} style={{ width: `${c * 100}%` }} /></div>
                      <span className="tabular text-[11px] text-muted-foreground">{Math.round(c * 100)}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
            {ext.fields.line_items && ext.fields.line_items.length > 0 && (
              <div className="mt-3 rounded-md border border-border p-2 text-xs">
                <div className="mb-1 font-medium">{ext.fields.line_items.length} line item(s)</div>
                {ext.fields.line_items.map((l, i) => <div key={i} className="flex justify-between gap-2"><span className="truncate">{l.name}</span><span className="tabular shrink-0">{l.qty ?? "?"} × {l.unit_price?.toLocaleString("en-IN") ?? "?"} = {l.amount?.toLocaleString("en-IN") ?? "?"}</span></div>)}
              </div>
            )}
          </div>
          <div className="grid content-start gap-4">
            <div>
              <div className="mb-1.5 text-xs font-semibold">Vendor match</div>
              {ext.vendor ? <div className="text-sm"><CircleCheck className="mr-1 inline size-4 text-allow" />{ext.vendor.name} <span className="text-xs text-muted-foreground">via {ext.vendor.method === "ntn" ? "NTN" : "fuzzy name"} ({Math.round(ext.vendor.confidence * 100)}%)</span></div>
                : <div className="text-sm text-review"><TriangleAlert className="mr-1 inline size-4" />No vendor matched: add the vendor first</div>}
            </div>
            <div>
              <div className="mb-1.5 text-xs font-semibold">Checks</div>
              <div className="grid gap-1">
                {ext.checks.map((c, i) => <div key={i} className={cn("flex items-start gap-1.5 text-xs", c.ok ? "text-muted-foreground" : "text-review")}>{c.ok ? <CircleCheck className="mt-px size-3.5 shrink-0 text-allow" /> : <TriangleAlert className="mt-px size-3.5 shrink-0" />}{c.text}</div>)}
                {ext.flags.map((f, i) => <div key={`f${i}`} className="flex items-start gap-1.5 text-xs text-blocked"><CircleAlert className="mt-px size-3.5 shrink-0" />{f}</div>)}
              </div>
            </div>
            {ext.status === "draft" && !it.score && (
              <div className="rounded-md bg-review-soft px-3 py-2 text-xs text-review">
                Some fields are below 80% confidence. Check the highlighted fields, then confirm.
                <Button size="sm" className="mt-2 w-full" disabled={saving || !ext.vendor} onClick={confirm}>{saving && <Loader2 className="animate-spin" />}Confirm fields & score</Button>
              </div>
            )}
            {it.score && (
              <div className={cn("rounded-md border p-3", it.score.decision === "blocked" ? "border-blocked/30 bg-blocked-soft/60" : it.score.decision === "review" ? "border-review/30 bg-review-soft/60" : "border-allow/30 bg-allow-soft/60")}>
                <div className="text-sm font-medium">{it.score.reasons.find((r) => r.engine !== "info" && !r.weak)?.text ?? "No significant risk signals"}</div>
                <div className="mt-2 flex gap-2">
                  {it.score.case_id && <Button asChild size="sm" variant="danger"><Link href={`/cases/${it.score.case_id}`}>Open case<ArrowRight /></Link></Button>}
                  <Button asChild size="sm" variant="outline"><Link href="/run">See it in the payment run</Link></Button>
                </div>
              </div>
            )}
            <details className="text-xs">
              <summary className="cursor-pointer font-semibold">Agent trace</summary>
              <div className="mt-2"><AgentTrace steps={[...ext.trace, ...(it.score?.trace ?? [])]} /></div>
            </details>
          </div>
        </div>
      )}
    </Card>
  );
}

