"use client";
import Link from "next/link";
import { useCallback, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, CircleAlert, CircleCheck, FileText, FileUp, Loader2, Plus, ScanText, TriangleAlert } from "lucide-react";
import { api, API_URL, getToken } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { Reason, TraceStep } from "@/lib/types";
import { PageTitle } from "@/components/app/shell";
import { DecisionBadge } from "@/components/app/decision";
import { AgentTrace } from "@/components/app/trace";
import { VendorCreateDialog } from "@/components/app/vendor-create-dialog";
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
type VendorOption = { id: number; name: string; status: string };

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
  const { data: samples, error: sampleError, reload: reloadSamples } = useApi<Sample[]>("/demo/samples");
  const { data: vendors, error: vendorError, reload: reloadVendors } = useApi<VendorOption[]>("/vendors");

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
      if (!res.ok) throw new Error("Could not download this demo sample. Please retry.");
      const blob = await res.blob();
      await handle(new File([blob], s.name, { type: "application/pdf" }));
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <>
      <PageTitle title="Upload invoices" sub="The document reader extracts fields into a strict schema; deterministic checks set the confidence. The LLM never decides." />
      <section aria-label="Document workflow" className="stagger mb-5 grid gap-3 sm:grid-cols-3">
        {[{ step: "01", title: "Read the document", text: "PDF text, OCR or Gemini extracts invoice fields." }, { step: "02", title: "Verify the fields", text: "Review confidence and deterministic validation checks." }, { step: "03", title: "Score the payment", text: "Risk engines decide; the document reader never sets a score." }].map((step) => <Card key={step.step} className="lift flex gap-3 p-4"><span className="text-xs font-semibold text-accent">{step.step}</span><div><h2 className="text-sm font-semibold">{step.title}</h2><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{step.text}</p></div></Card>)}
      </section>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); Array.from(e.dataTransfer.files).forEach(handle); }}
        className={cn("group flex animate-rise-in cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed bg-card px-6 py-10 text-center transition-all duration-300 [animation-delay:120ms]",
          drag ? "scale-[1.01] border-accent bg-accent-soft" : "border-border hover:border-accent/50")}
      >
        <div className={cn("flex size-14 items-center justify-center rounded-2xl bg-accent-soft transition-transform duration-300 group-hover:-translate-y-1", drag && "-translate-y-1.5 scale-110")}><FileUp aria-hidden className="size-6 text-accent" /></div>
        <div className="text-sm font-semibold">Drop invoice PDFs or images here</div>
        <div className="text-xs text-muted-foreground">PDF, PNG, JPG · up to 8 MB per file</div>
        <Button variant="outline" onClick={() => input.current?.click()}><FileUp />Choose invoice files</Button>
        <input aria-label="Invoice files" ref={input} type="file" accept=".pdf,image/*" multiple hidden onChange={(e) => Array.from(e.target.files ?? []).forEach(handle)} />
      </div>
      {samples && samples.length > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-muted/30 p-4 text-xs">
          <span className="text-muted-foreground">Demo samples:</span>
          {samples.map((s) => (
            <Button key={s.group + s.name} size="sm" variant="outline" className="max-w-full" onClick={() => loadSample(s)} title={`${s.hint}: ${s.name}`}>
              <FileText /><span className="min-w-0 truncate">{s.hint}: {s.name.replace(/^resent_|^new_/, "").slice(0, 26)}</span>
            </Button>
          ))}
        </div>
      )}
      {sampleError && <div role="alert" className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-4 text-sm"><CircleAlert className="size-4 text-blocked" /><span className="min-w-0 flex-1">Demo samples unavailable: {sampleError.message}</span><Button size="sm" variant="outline" onClick={() => void reloadSamples()}>Retry samples</Button></div>}
      <div className="mt-6 grid gap-4">
        {items.map((it) => <UploadCard key={it.key} it={it} vendors={vendors} vendorError={vendorError?.message} onReloadVendors={reloadVendors} onRescore={score} onUpdate={(p) => update(it.key, p)} />)}
      </div>
    </>
  );
}

function UploadCard({ it, vendors, vendorError, onReloadVendors, onRescore, onUpdate }: { it: Item; vendors: VendorOption[] | null; vendorError?: string; onReloadVendors: () => Promise<void>; onRescore: (key: string, id: number) => void; onUpdate: (p: Partial<Item>) => void }) {
  const ext = it.ext;
  const { user } = useAuth();
  const prefix = useId();
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [vendorChoice, setVendorChoice] = useState<string | null>(null);
  const [createdVendor, setCreatedVendor] = useState<VendorOption | null>(null);
  const [creatingVendor, setCreatingVendor] = useState(false);
  const selectedVendorId = vendorChoice ?? (ext?.vendor ? String(ext.vendor.id) : "");
  const canCreateVendor = user?.role === "owner" || user?.role === "accountant";
  const vendorOptions = [...(vendors ?? [])];
  if (createdVendor && !vendorOptions.some((vendor) => vendor.id === createdVendor.id)) vendorOptions.push(createdVendor);
  if (ext?.vendor && !vendorOptions.some((vendor) => vendor.id === ext.vendor?.id)) vendorOptions.push({ ...ext.vendor, status: "unknown" });
  async function confirm() {
    if (!ext || !selectedVendorId) return;
    setSaving(true);
    setSaveError(null);
    try {
      const body: Record<string, unknown> = { confirm: true, vendor_id: Number(selectedVendorId) };
      const correctedFields: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(edits)) {
        if (["subtotal", "tax", "total"].includes(k)) {
          const amount = Number(v.replace(/,/g, ""));
          if (!v.trim() || !Number.isFinite(amount) || amount < 0) throw new Error(`${FIELD_LABEL[k]} must be a non-negative amount.`);
          body[k] = amount;
        }
        else if (["invoice_no", "invoice_date", "due_date"].includes(k)) body[k] = v;
        if (body[k] !== undefined) correctedFields[k] = body[k];
      }
      const saved = await api.patch<{ status: string; vendor_id: number; vendor: string }>(`/invoices/${ext.invoice_id}`, body);
      const manualMatch = String(ext.vendor?.id) !== selectedVendorId;
      onUpdate({ error: undefined, ext: { ...ext, fields: { ...ext.fields, ...correctedFields }, status: saved.status, ready_to_score: true, vendor: manualMatch ? { id: saved.vendor_id, name: saved.vendor, method: "manual", confidence: 0 } : ext.vendor } });
      onRescore(it.key, ext.invoice_id);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Card className="animate-rise-in overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <FileText className="size-4 text-muted-foreground" />
        <div className="min-w-0 flex-1 truncate text-sm font-medium">{it.name}</div>
        {ext && <Badge variant={ext.cached ? "default" : "accent"}><ScanText className="size-3.5" />{ENGINE_LABEL[ext.engine] ?? ext.engine}{ext.cached ? " · cached" : ""}</Badge>}
        {it.state === "uploading" && <Badge variant="outline"><Loader2 className="size-3.5 animate-spin" />Reading document…</Badge>}
        {it.state === "scoring" && <Badge variant="outline"><Loader2 className="size-3.5 animate-spin" />Scoring…</Badge>}
        {it.score && <DecisionBadge decision={it.score.decision} large />}
        {it.score && <span className="tabular text-sm font-semibold">{it.score.score}/100</span>}
      </div>
      {it.state === "error" && <div role="alert" className="flex flex-wrap items-center gap-2 px-4 py-3 text-sm text-blocked"><CircleAlert className="size-4" /><span className="min-w-0 flex-1">{it.error}</span>{ext && ext.status !== "draft" && <Button size="sm" variant="outline" onClick={() => onRescore(it.key, ext.invoice_id)}>Retry scoring</Button>}</div>}
      {ext && (
        <div className="grid gap-5 p-4 lg:grid-cols-[1.2fr_1fr]">
          <div className="min-w-0">
            <div className="mb-3 flex justify-between text-xs font-semibold"><span>Extracted fields</span><span className="text-muted-foreground">Confidence</span></div>
            <div className="grid gap-1">
              {Object.keys(FIELD_LABEL).map((f, i) => {
                const v = ext.fields[f];
                const c = ext.confidence[f] ?? 0;
                const low = c < 0.8;
                const editable = ext.status === "draft" && ["invoice_no", "invoice_date", "due_date", "subtotal", "tax", "total"].includes(f);
                return (
                  <div key={f} className={cn("fill-in grid grid-cols-[90px_minmax(0,1fr)_65px] sm:grid-cols-[110px_minmax(0,1fr)_70px] items-center gap-2 rounded-lg px-2 py-2 text-sm", low && "bg-review-soft")} style={{ animationDelay: `${i * 60}ms` }}>
                    <div className="text-xs text-muted-foreground">{FIELD_LABEL[f]}</div>
                    {editable ? (
                      <Input aria-label={`Correct ${FIELD_LABEL[f]}`} className="h-8 text-sm" defaultValue={v == null ? "" : String(v)} disabled={saving} onChange={(e) => setEdits((x) => ({ ...x, [f]: e.target.value }))} />
                    ) : (
                      <div className={cn("truncate font-mono text-[13px]", v == null && "text-muted-foreground")}>{v == null ? "not found" : typeof v === "number" ? v.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : String(v)}</div>
                    )}
                    <div className="flex items-center gap-1">
                      <div className="h-1.5 w-8 overflow-hidden rounded-full bg-muted"><div className={cn("grow-x h-full", low ? "bg-review" : "bg-allow")} style={{ width: `${c * 100}%` }} /></div>
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
              {ext.vendor ? <div className="text-sm"><CircleCheck className="mr-1 inline size-4 text-allow" />{ext.vendor.name} <span className="text-xs text-muted-foreground">{ext.vendor.method === "manual" ? "manually selected" : `via ${ext.vendor.method === "ntn" ? "NTN" : "fuzzy name"} (${Math.round(ext.vendor.confidence * 100)}%)`}</span></div>
                : <p className="text-sm text-review"><TriangleAlert className="mr-1 inline size-4" />No vendor matched. Select a vendor or add one below.</p>}
              {ext.status === "draft" && !it.score && <div className="mt-3 grid gap-2">
                <label htmlFor={`${prefix}-vendor`} className="text-xs font-medium text-muted-foreground">Match invoice to vendor</label>
                <select id={`${prefix}-vendor`} value={selectedVendorId} disabled={saving} onChange={(event) => setVendorChoice(event.target.value)} className="h-10 w-full min-w-0 rounded-md border border-border bg-card px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><option value="">Select a vendor</option>{vendorOptions.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}{vendor.status === "blocked" ? " (blocked)" : ""}</option>)}</select>
                {vendorError ? <p role="alert" className="text-xs text-blocked">{vendorError} <button type="button" className="rounded font-medium underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => void onReloadVendors()}>Retry vendor list</button></p> : !vendors && <p role="status" className="text-xs text-muted-foreground">Loading vendor list…</p>}
                {canCreateVendor ? <Button size="sm" variant="outline" className="justify-self-start" onClick={() => setCreatingVendor(true)}><Plus />Add vendor</Button> : <p className="text-xs text-muted-foreground">Ask an accountant or owner to add a vendor if it is missing.</p>}
                {vendorChoice !== null && selectedVendorId && <p className="text-xs text-muted-foreground">Your vendor selection will be saved when you confirm the fields.</p>}
              </div>}
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
                Review the extracted fields and vendor match. Highlighted fields have low extraction confidence; confirmation is required before scoring.
                {saveError && <p role="alert" className="mt-2 rounded-md bg-card px-2 py-2 text-blocked">{saveError}</p>}
                <Button size="sm" className="mt-2 w-full" disabled={saving || !selectedVendorId} onClick={confirm}>{saving && <Loader2 className="animate-spin" />}Confirm fields & score</Button>
              </div>
            )}
            {it.score && (
              <div className={cn("animate-rise-in rounded-md border p-3", it.score.decision === "blocked" ? "border-blocked/30 bg-blocked-soft/60" : it.score.decision === "review" ? "border-review/30 bg-review-soft/60" : "border-allow/30 bg-allow-soft/60")}>
                <div className="text-sm font-medium">{it.score.reasons.find((r) => r.engine !== "info" && !r.weak)?.text ?? "No significant risk signals"}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {it.score.case_id && <Button asChild size="sm" variant="danger"><Link href={`/cases/${it.score.case_id}`}>Open case<ArrowRight /></Link></Button>}
                  <Button asChild size="sm" variant="outline"><Link href={`/flagged?view=${it.score.decision === "allow" ? "all" : "flagged"}`}>See it in Flagged invoices</Link></Button>
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
      {canCreateVendor && ext && <VendorCreateDialog open={creatingVendor} onOpenChange={setCreatingVendor} initial={{ name: String(ext.fields.vendor_name ?? ""), ntn: String(ext.fields.ntn ?? ""), strn: String(ext.fields.strn ?? ""), iban: String(ext.fields.iban ?? "") }} onCreated={(vendor) => { setCreatedVendor({ ...vendor, status: "active" }); setVendorChoice(String(vendor.id)); void onReloadVendors(); }} />}
    </Card>
  );
}

