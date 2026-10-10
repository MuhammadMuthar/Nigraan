"use client";

import { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";

type VendorFields = {
  name: string; ntn: string; strn: string; category: string; phone: string; address: string;
  iban: string; bank_name: string; payment_terms_days: string;
};

export function VendorCreateDialog({ open, onOpenChange, initial, onCreated }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial?: Partial<VendorFields>;
  onCreated: (vendor: { id: number; name: string }) => void;
}) {
  const prefix = useId();
  const [fields, setFields] = useState<VendorFields>({ name: "", ntn: "", strn: "", category: "staples", phone: "", address: "", iban: "", bank_name: "", payment_terms_days: "30", ...initial });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ id: number }>("/vendors", {
        ...fields, name: fields.name.trim(), category: fields.category.trim(), phone: fields.phone.trim(),
        address: fields.address.trim(), bank_name: fields.bank_name.trim(),
        ntn: fields.ntn.trim() || null, strn: fields.strn.trim() || null,
        iban: fields.iban.replace(/\s/g, "").toUpperCase(), payment_terms_days: Number(fields.payment_terms_days),
      });
      toast.success("Vendor created");
      onOpenChange(false);
      onCreated({ id: result.id, name: fields.name.trim() });
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  function field(key: keyof VendorFields, label: string, options: React.InputHTMLAttributes<HTMLInputElement> = {}) {
    const invalid = error instanceof ApiError && error.field === key;
    return <div className="grid gap-1.5">
      <Label htmlFor={`${prefix}-${key}`}>{label}</Label>
      <Input id={`${prefix}-${key}`} value={fields[key]} onChange={(event) => setFields((value) => ({ ...value, [key]: event.target.value }))} aria-invalid={invalid || undefined} aria-describedby={invalid ? `${prefix}-error` : undefined} disabled={busy} {...options} />
    </div>;
  }

  return <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
    <DialogContent className="max-h-[90dvh] overflow-y-auto">
      <DialogTitle>Add vendor</DialogTitle>
      <DialogDescription>Verify the vendor and bank details before saving. Later bank changes require a different user&apos;s approval.</DialogDescription>
      <form onSubmit={create} className="mt-5 grid gap-4">
        {field("name", "Vendor name", { required: true, minLength: 2, autoComplete: "organization" })}
        <div className="grid gap-4 sm:grid-cols-2">
          {field("ntn", "NTN (optional)")}
          {field("strn", "STRN (optional)")}
          {field("category", "Category", { required: true })}
          {field("payment_terms_days", "Payment terms (days)", { type: "number", min: 0, step: 1, required: true })}
        </div>
        {field("phone", "Contact phone", { type: "tel", autoComplete: "tel", required: true })}
        {field("address", "Business address", { autoComplete: "street-address", required: true })}
        <div className="border-t border-border pt-4">
          <h3 className="mb-3 text-sm font-semibold">Initial bank account</h3>
          <div className="grid gap-4">
            {field("bank_name", "Bank name", { required: true, placeholder: "e.g. HBL" })}
            {field("iban", "Pakistan IBAN", { required: true, autoComplete: "off", spellCheck: false, placeholder: "PK…", className: "font-mono uppercase" })}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Nigraan validates the check digit and stores a hash plus the final four characters.</p>
        </div>
        {error && <p id={`${prefix}-error`} role="alert" className="rounded-lg border border-blocked/20 bg-blocked-soft p-3 text-sm text-blocked">{error.message}</p>}
        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />}{busy ? "Saving vendor…" : "Create vendor"}</Button>
        </div>
      </form>
    </DialogContent>
  </Dialog>;
}
