import { FlaskConical, Scale } from "lucide-react";
import { pct } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type EvaluationMetrics = { recall: number; false_alarm_rate: number; pr_auc: number; alerts: number };
export type ReviewEvaluation = {
  model_version: string; generated_at: string; seed: number; test_period: string;
  n_payments: number; n_fraud: number;
  rules_comparison: { nigraan: EvaluationMetrics; simple: EvaluationMetrics; expert: EvaluationMetrics; expert_description: string; note: string };
  invoice_age_ablation: {
    trained_rows: number; with_feature: EvaluationMetrics; without_feature: EvaluationMetrics;
    risk_model_only: { with_invoice_age_pr_auc: number; without_invoice_age_pr_auc: number };
    method: string; note: string;
  };
  limitations: string[];
};

export function ReviewEvaluationCards({ evaluation: e }: { evaluation: ReviewEvaluation }) {
  const a = e.invoice_age_ablation;
  return <section aria-label="Review evaluation" className="mt-5 grid gap-5 xl:grid-cols-2">
    <Card>
      <CardHeader>
        <Badge variant="outline" className="mb-2 w-fit">Synthetic hold-out · stronger comparator</Badge>
        <CardTitle className="flex items-center gap-2"><Scale className="size-4 text-accent" />Expert rules comparison</CardTitle>
        <CardDescription>{e.n_payments} payments · {e.n_fraud} planted frauds · {e.test_period} · seed {e.seed}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Held-out recall and false alarms for the firewall and deterministic rule checks</caption>
            <thead><tr className="border-b border-border text-xs text-muted-foreground"><th scope="col" className="pb-3">System</th><th scope="col" className="pb-3 text-right">Fraud caught</th><th scope="col" className="pb-3 text-right">False alarms</th></tr></thead>
            <tbody>{([["Nigraan firewall", e.rules_comparison.nigraan], ["Simple rules", e.rules_comparison.simple], ["Expert rules", e.rules_comparison.expert]] as const).map(([name, metrics]) => <tr key={name} className="border-b border-border last:border-0"><th scope="row" className="py-3 font-medium">{name}</th><td className="tabular py-3 text-right">{pct(metrics.recall, 1)}</td><td className="tabular py-3 text-right">{pct(metrics.false_alarm_rate, 1)}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{e.rules_comparison.expert_description}</p>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{e.rules_comparison.note}</p>
      </CardContent>
    </Card>
    <Card>
      <CardHeader>
        <Badge variant="outline" className="mb-2 w-fit">Synthetic-data sensitivity study</Badge>
        <CardTitle className="flex items-center gap-2"><FlaskConical className="size-4 text-accent" />Without the invoice-age feature</CardTitle>
        <CardDescription>Offline comparison refit on {a.trained_rows} historical rows; shipped models remain unchanged.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-border p-4"><p className="text-xs text-muted-foreground">Firewall recall · with age</p><p className="tabular mt-2 text-2xl font-semibold">{pct(a.with_feature.recall, 1)}</p></div>
          <div className="rounded-xl border border-border p-4"><p className="text-xs text-muted-foreground">Firewall recall · without age</p><p className="tabular mt-2 text-2xl font-semibold">{pct(a.without_feature.recall, 1)}</p></div>
        </div>
        <p className="mt-3 text-sm">False alarms without age: <b className="tabular">{pct(a.without_feature.false_alarm_rate, 1)}</b>. Risk-model PR-AUC: <span className="tabular">{a.risk_model_only.with_invoice_age_pr_auc.toFixed(3)} → {a.risk_model_only.without_invoice_age_pr_auc.toFixed(3)}</span>.</p>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{a.method}</p>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{a.note}</p>
      </CardContent>
    </Card>
    <p className="text-xs leading-relaxed text-muted-foreground xl:col-span-2">{e.limitations.join(" ")} Model {e.model_version} · evaluated {e.generated_at.slice(0, 10)}. Results are shown only while the saved model artifacts match.</p>
  </section>;
}
