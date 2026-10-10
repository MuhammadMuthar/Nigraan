export type Decision = "allow" | "review" | "blocked" | "unscored";

export type Reason = { engine: string; text: string; weight: number; feature?: string; contribution?: number; code?: string; weak?: boolean };
export type TraceStep = { step: string; label: string; ms: number; detail: string };
export type RulesCheck = { code: string; text: string };
export type RuleComparison = { name: string; flagged: boolean; checks: RulesCheck[] };
export type RulesComparison = { simple: RuleComparison; expert: RuleComparison };
export type RunRulesComparison = {
  simple: { name: string; flagged_count: number; flagged_amount: number; nigraan_additional_count: number; nigraan_additional_amount: number };
  expert: { name: string; flagged_count: number; flagged_amount: number; nigraan_additional_count: number; nigraan_additional_amount: number };
  note: string;
};

export type RunLine = {
  id: number; invoice_id: number; invoice_no: string; vendor_id: number; vendor: string; amount: number; amount_fmt: string;
  status: string; decision: Decision; model_decision: Decision | null; score: number | null; top_reason: string | null;
  reasons: Reason[]; info: string[]; fraud_type: string | null; created_by: string | null; created_by_id: number | null;
  created_at: string; approved_by: string | null; pay_date: string; override: string | null; bank_last4: string; bank_name: string;
  model_version: string | null; case: { id: number; status: string } | null;
  rules_comparison: RulesComparison; vendor_commitment_amount: number; requires_owner_approval: boolean;
  override_by_id: number | null; override_by: string | null;
};

export type PanelCase = { low_point: number; low_point_day: string; first_breach: string | null; breach_gap: number; stays_above_reserve: boolean };

export type ReceivableRow = {
  receivable_id?: number; id?: number; customer_id: number; customer: string; segment: string; invoice_no: string; amount: number;
  amount_fmt?: string; due_date: string; expected_date: string | null; overdue_days: number | null; basis?: string; note?: string | null;
  limited_history: boolean; risk: number | null; reasons: string[]; disputed?: number; median_delay?: number;
  included_in_base?: boolean;
};

export type CollectionPolicy = {
  name: string; label: string; unconfirmed_count: number; unconfirmed_amount: number;
};
export type CashValidation = {
  forecast_horizon_weeks: number; backtest_horizon_weeks: number | null; origins: string[];
  synthetic: boolean; seed: number | null; receipt_policy: string; current_policy_backtested: boolean;
  mae_rupees_per_week: number | null; wape: number | null; generated_at: string | null; scope: string;
  due_date_mae_rupees_per_week: number | null; improvement_vs_due_date: number | null;
};

export type CashPanel = {
  as_of: string; cash_before_run: number; reserve: number; run_total: number;
  totals_by_decision: Record<string, number>; blocked_amount: number;
  with_nigraan: PanelCase; release_everything: PanelCase; hold_yellow: PanelCase;
  responsible_receivables: ReceivableRow[];
  chart: { day: string; with_nigraan: number; release_everything: number }[];
  collection_policy: CollectionPolicy; validation: CashValidation;
};

export type RunDetail = {
  id: number; name: string; run_date: string; status: string; created_at: string; lines: RunLine[];
  totals: Record<"allow" | "review" | "blocked", { count: number; amount: number }>; open_lines: number;
  approval_limit: number; model_version: string; can_export: boolean; cash: CashPanel;
  rules_comparison: RunRulesComparison; approval_policy: string;
};

export type Week = {
  week: number; start: string; end: string; inflow: number; outflow: number;
  inflow_by_basis: Record<string, number>; outflow_by_basis: Record<string, number>; closing: number; low: number; low_day: string;
};
export type Projection = {
  as_of: string; opening: number; reserve: number; low_point: number; low_point_day: string; first_breach: string | null;
  breach_gap: number; total_in: number; total_out: number; weeks: Week[];
  days?: { day: string; inflow: number; outflow: number; closing: number }[];
  beyond_horizon: { day: string; amount: number; label: string; ref: string }[];
};
