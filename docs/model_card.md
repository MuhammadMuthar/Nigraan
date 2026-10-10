# Model card: Nigraan

All numbers below come from `python -m ml.evaluate --months 11-12 --seeds 42,43,44,45,46` and are stored in [`models/metrics.json`](../models/metrics.json). Re-run that command to reproduce them.

## Data provenance

- **100% synthetic.** `python -m data_gen.generate_company --seed 42` builds *Bismillah Distributors (fictional)*, an FMCG distributor in Lahore:
  - 60 vendors with Pakistani names, home banks (HBL, MCB, Meezan, UBL, Allied), item mixes, invoicing rhythms and price drift, plus 1-2 legit price revisions a year;
  - 138 items, ~4.2k vendor invoices and ~4.0k payments in 52 weekly runs;
  - 45 employees and 4 users;
  - 80 credit customers with hidden payment profiles (punctual, chronic, seasonal around Eid, deteriorating, new) and ~3.5k receivables;
  - Eid slow-downs and a pre-June peak.
- **Planted frauds (~2.5% of payments)**, ground truth in a hidden `labels.csv` that the app never reads:

  | Type | What is planted | Variants |
  |---|---|---|
  | F1 | Duplicate / near-duplicate invoice | Zero-pad, dash, prefix, suffix and renumbered copies; date ±1-5 days; amount within <1% |
  | F2 | Bank-detail change scam | Account changed 1-6 days before the payment by a rare editor via email/phone. 25% stealth: forged letter processed by the usual clerk |
  | F3 | Shell vendor sharing an employee's phone, bank or address | 25% stealth: registered, taxed, concrete items |
  | F4 | Inflated unit price | 1.3-3× the item's normal price |
  | F5 | Split payments under the Rs 5 lakh approval limit within 48 h | 20% split further under the limit |
  | F7 | Approver enters and self-approves at night or on a holiday | 25% weekday evenings |

- **Realism added on purpose**:
  - a disclosed related-party vendor;
  - sister concerns sharing an office;
  - legit late-night month-end entries and owner-entered urgent payments;
  - legit bank changes;
  - payments above the approval limit;
  - instalments;
  - disputed receivables.

## Fraud firewall

| Engine | Model | Inputs | Why AI, not rules |
|---|---|---|---|
| Duplicate detector | Logistic regression (sklearn) | Pair features vs earlier invoices of the same or fuzzy-matched vendor (±90 days, ±2%): normalised-number similarity, numeric gap, date gap, amount difference, line-item Jaccard, TF-IDF char n-gram cosine | Exact-match rules miss `INV-0102` vs `INV-102` with a 0.5% amount change, yet fire on legit weekly standing orders |
| Risk model | XGBoost, SHAP reasons via `pred_contribs` | 27 behaviour features at payment time: amount vs vendor history, unit price vs item and vendor price, bank-change age/source/editor, first payment to an account, vendor age, round amounts, same payee in 48 h, approval-limit gap, entry hour, Sunday/holiday, creator can approve, vague items, days since invoice date | Fraud is a combination of weak signals; thresholds per feature either flood or miss |
| Anomaly detector | Isolation Forest (contamination 0.03), normalised to 0-1 above the training 90th percentile | Compact imputed feature subset | For patterns not in the labelled history |
| Relationship graph | Deterministic NetworkX matching with time-valid edges | Vendors, employees, users, bank hashes, phones, normalised addresses, CNIC hashes | Finds vendor → phone → employee paths. Disclosed related parties are down-weighted (×0.2). This engine is not a learned model. |
| Rules | Deterministic | Exact duplicate (same vendor + normalised number + total), blocked vendor/account → red; split-payment pattern → at least yellow | Certain cases need no model |

**Fusion.** Compute the weighted raw signal `Σ wᵢ·signalᵢ`, rescale it using the tuned yellow/red thresholds, then take `score = max(100 × rule_hit, rescaled_signal)`. The rescaling is piecewise linear; the displayed score is not a fraud probability.

- Tuned weights: risk model 0.5, anomaly 0.1, duplicate 0.5, graph 0.5.
- Thresholds: t_yellow 0.088 → 40, t_red 0.274 → 75 (piecewise-linear, monotone).
- Tuned on two out-of-time folds (months 7-8, 9-10) for maximum recall subject to false alarms ≤ 4%, red false alarms ≤ 0.5%, and "a 0.9 duplicate or graph signal alone reaches red".
- Decisions: < 40 Allow, 40-74 Review (second approver, not the creator), ≥ 75 Blocked (locked, case opened).

**Prediction moment** = payment creation. Every feature uses only rows dated strictly before it; `tests/test_scoring.py::test_no_feature_uses_data_after_prediction_moment` proves this by truncating the ledger.

**Excluded leakage fields**: the realised approver, approval time, release status, later account blocks, case outcomes and invoice payment status.

**Split**: train months 1-10 (Oct 2025-Jul 2026, labels = audited historical cases), tune on folds inside months 7-10, final refit on 1-10, **test on months 11-12 (Aug-Sep 2026), never seen**.

### Results (held-out months 11-12, seed 42: 638 payments, 22 frauds)

| Metric | Nigraan | Rules-only baseline (exact duplicate number OR amount over limit) |
|---|---|---|
| Recall (yellow or red) | **100%** | 22.7% |
| Recall at red | **95.5%** | 22.7% |
| Precision at red | **95.5%** | 20.0% |
| False-alarm rate (legit flagged yellow or red) | **3.6%** | 3.2% |
| False-alarm rate at red | 0.2% | — |
| PR-AUC | **0.993** | 0.07 |
| Rupees caught at red | Rs 53,51,611 of Rs 54,26,100 (98.6%) | Rs 12,64,852 |

Per type (caught/n): F1 6/6 · F2 4/4 · F3 3/3 · F4 3/3 · F5 4/4 · F7 2/2. Scoring takes about 8 ms per payment once the ledger context is built (about 0.4 s); a 40-line run scores in about 1 s.

**Ablation** (zero one engine's weight, keep thresholds):

| Without | Recall | False alarms |
|---|---|---|
| Risk model | 68% | 1.6% |
| Duplicate detector | 91% | 3.2% |
| Graph | 100% | 2.9% |
| Anomaly | 100% | 1.9% |

The Isolation Forest adds false alarms and no recall on these planted types. It stays, at a small weight, for unseen patterns; we report this rather than hide it. On the tuning folds, the brief's default weights (0.4/0.2/0.2/0.2) gave the same alert recall but lower red recall (97.1% vs 100%) and lower PR-AUC (0.962 vs 0.973).

**Robustness** (5 different synthetic companies, seeds 42-46, each generated, trained and tested independently; 90 frauds pooled):

| | Result |
|---|---|
| Recall | 100% |
| Recall at red | 97.8% |
| Precision at red | 88% |
| False-alarm rate | 2.4% (per seed 1.4-3.6%) |
| PR-AUC (mean) | 0.98 |
| Rules-only recall (mean) | 32% |

Every type stays ≥ 70% (all at 100% alert recall).

### Review study: stronger rules and invoice-age sensitivity

[review_eval.json](../models/review_eval.json) adds a reproducible comparison on the same 638 held-out payments (22 planted frauds). Its model version and SHA-256 fingerprints must match the shipped artifacts before the API displays it. `python -m ml.review_evaluate` writes this separate study without replacing production models.

| System | Fraud caught (yellow/red) | Legitimate payments flagged |
| --- | --- | --- |
| Shipped firewall | 22/22 (100%) | 22/616 (3.6%) |
| Simple rules (number repeated or individual amount over limit) | 5/22 (22.7%) | 20/616 (3.2%) |
| Expert rules | 19/22 (86.4%) | 147/616 (23.9%) |
| Firewall refit without invoice-age feature | 22/22 (100%) | 25/616 (4.1%) |

Expert rules use explicit review thresholds for recent bank changes, new vendors, night entry, inflated prices and combined payee exposure, plus deterministic policy and relationship checks. They exclude invoice age. These broad checks were not optimized to match the firewall's false-alarm rate; the results do not establish superiority over all possible rules. Live run comparisons describe actual flags and amounts, not accuracy or proven fraud. Graph and split checks are deterministic.

The sensitivity study refits XGBoost and Isolation Forest on the same historical training data without `days_since_invoice_date`; it keeps the shipped duplicate model, graph/policy engines and fusion thresholds, with no retuning. Strong recall in this single synthetic test does not establish real-world generalization. Small planted-fraud counts and synthetic signatures remain important limits.

## Late-payment model

- **Target**: receivable fully paid after its due date (0 grace days). Unpaid past due at the data end also counts as late. Not-yet-due invoices are excluded as unknown (122 in the test window).
- **Prediction moment**: issue date. Features use only the customer's history settled before it:
  - amount, terms, issue month, Eid period, June year-end;
  - prior settled count, prior late fraction, median and std of prior delay, recent-delay trend;
  - days since last payment, open and overdue invoices at issue;
  - tenure, amount vs customer median, segment.
- **Selection**: baseline vs logistic regression vs XGBoost, trained on months 1-8 and chosen on months 9-10 PR-AUC. XGBoost won on validation (0.83 vs LR 0.72 vs baseline 0.57), then was refit on months 1-10.

| Held-out months 11-12 (396 receivables, late rate 57%) | PR-AUC | Precision in top 20% | Brier |
|---|---|---|---|
| Late-rate baseline | 0.57 | 57% | 0.250 |
| Logistic regression | 0.89 | 96% | 0.154 |
| **XGBoost (shipped)** | **0.91** | **99%** | **0.137** |

The reliability check failed our strict rule (max bin gap ≤ 0.12), so the UI calls the output a "late-payment risk score", not a probability. Customers with fewer than 5 settled invoices get a "limited history" badge and their segment's training late rate instead of a model score (10% of test receivables).

## Cash forecast

The deterministic engine (`services/cash/engine.py`) computes `closing = opening + expected receipts − scheduled outflows − approved payments` daily, then aggregates into 13 weeks. It catches a mid-week breach, lists receipts beyond 91 days separately, and excludes disputed amounts.

**Backtest.** Rolling weekly origins in months 11-12, 4-week horizon, projecting receipts of the receivables open at each origin vs what was actually collected:

| Method | Mean absolute error per week | WAPE |
|---|---|---|
| Everyone pays on the due date (baseline) | Rs 60.4 lakh | 0.66 |
| **Due date + customer's median past delay (original next-week assumption policy)** | **Rs 35.4 lakh** | **0.39** |

That is 41% lower weekly error.

**Current conservative collection policy.** A stale receivable beyond both the customer's median and slow-payer delay has no confirmed collection date. It is excluded from base cash and listed as an unconfirmed assumption. An explicit dated What-if scenario may include it without changing the books. Historical phone/payment evidence and account amounts remain facts; a future collection date remains an estimate or assumption.

The original table above reproduces the older next-week assumption policy. [cash_review_metrics.json](../models/cash_review_metrics.json), produced by `python -m ml.cash_review`, compares both policies on the same five rolling origins (3–31 August 2026), four weeks each, synthetic seed 42:

| Current policy method | Mean absolute weekly receipt error | WAPE |
| --- | --- | --- |
| Due dates; unconfirmed overdue excluded | Rs 25,93,299.50 | 0.284 |
| Median delay; unconfirmed overdue excluded | Rs 21,99,658.50 | 0.241 |

The current median-delay policy reduces error by **15.2%** against its matching due-date baseline. This measures four-week receipts only; it does not validate 13-week balances, payment forecasts or reserve outcomes. The additive artifact is checked against the receipt-policy source hash before its results are shown.

## Document reader

Gemini Flash (JSON schema, temperature 0, default 8 s timeout per HTTP attempt, one retry, cached by file hash) cross-checked by PDF-text/Tesseract + regex and deterministic validators (line sums, 18% tax, NTN format, IBAN mod-97). Upload extraction runs in a worker thread, so it does not block other API requests. The timeout is not a total extraction deadline: retries and PDF/OCR can take additional time. On the 40 demo-week PDFs, the regex fallback alone extracts **100% of fields** (400/400) and all line items. **Caveat:** that fallback was written for these three invoice layouts, so this proves the pipeline, not accuracy on unseen layouts. No new Gemini measurement is claimed without configured credentials and an actual evaluation.

## LLM use and guardrails

The LLM writes case summaries from **structured evidence only**; invoice text is never put in the prompt (prompt-injection safety). Every number in its output must appear in the evidence, or the summary is hidden and the evidence list is shown instead. Without a key, a deterministic template is used and labelled as such. The LLM never produces a score, a decision or a cash number.

## Limitations

- **Synthetic data proves the pipeline, not real-world accuracy. A pilot with one distributor's real ledger is the next step.**
- Planted frauds have recognisable signatures even with the stealth variants, so real fraud will be harder. Expect lower recall and more false alarms.
- Test windows are small (22 frauds for seed 42), which is why we report 5-seed robustness. Per-type counts on one seed are not statistically meaningful.
- No new sales or purchases are forecast in the 13-week projection.
- The late-payment output is a risk score, not a calibrated probability.
- Retraining refits the engines but keeps the tuned fusion weights and thresholds so the UI bands stay stable; re-tuning needs `ml.train_all`.
