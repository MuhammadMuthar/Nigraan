# Claude review implementation and AICON’26 readiness

Implemented the review's immediate fixes and the live rules comparison, invoice-age study, evidence-based verification and conservative cash assumptions. The frontend remains the existing Next.js application; APIs are extended for verification/comparison metadata. No production model artifact, demo invoice dataset, money representation, scoring threshold or bank settlement state was replaced.

## What changed

- Upload extraction uses FastAPI's worker pool with an 8 MB bounded read; the optional Gemini timeout defaults to eight seconds **per attempt**, with one retry.
- Only the owner can reset demo data, with matching navigation permissions.
- Case outcomes require an evidence reference, completed checks, verification method, supporting result and substantive finding. The case clearer cannot approve the recovered payment.
- Approval limits cover each vendor's combined pending/approved/exported exposure in the current run. Held, blocked, rejected and settled instructions are excluded; this does not add cross-run purchase aggregation.
- Automatic suspected patterns use displayed evidence, including existing stored cases and bilingual summaries. Invoice age does not imply out-of-hours activity; onboarding does not imply a bank change. Historical confirmed labels remain intact.
- Current-run simple/expert comparisons use real line counts and exact paisa amounts. Learned near-duplicate/risk/anomaly models are distinguished from deterministic rules and relationship checks.
- Dashboard exposes a hash-validated expert comparator and invoice-age sensitivity study, preserves the evaluated model version, and counts currently locked lines accurately. It has a recoverable service-error state.
- Stale collections have no invented future date and are excluded from base cash. What-if can explicitly date one as an assumption without altering the ledger. The UI distinguishes 13 projected weeks from four evaluated receipt weeks.
- The five-minute guide maps the provided judging rubric to working evidence and includes buyer/pricing hypotheses and an interview/pilot plan.

## Measured results

All results are synthetic; this is one company with 22 planted frauds in 638 held-out payments.

| System | Fraud recall | False alarms |
| --- | --- | --- |
| Shipped Nigraan firewall | 100% | 3.6% |
| Simple rules | 22.7% | 3.2% |
| Expert rules | 86.4% | 23.9% |
| Offline refit without invoice age | 100% | 4.1% |

Expert rules are broad predefined checks, not calibrated to a matching false-alarm rate. The age study refits XGBoost/Isolation Forest offline with fixed fusion thresholds; it does not replace the shipped models or prove generalization. Model fingerprints invalidate the saved study after retraining.

Current conservative cash receipts have mean absolute weekly error of Rs 21,99,658.50 versus Rs 25,93,299.50 for the matching due-date baseline (15.18% lower), across five rolling origins and four weeks per origin. This does not validate 13-week balances or reserve outcomes. The original 41% receipt result remains labelled as the older next-week assumption policy.

## Validation

Validated on 10 October 2026 against the final application changes:

- Backend: `python -m pytest -q` — **126 passed** on isolated SQLite; one existing Starlette/httpx deprecation warning.
- Frontend: `npm run typecheck`, `npm run lint`, `npm run build` — **passed**; lint retains two existing navigation warnings.
- Browser: `PW_CHROMIUM=/usr/bin/chromium npm run test:e2e` — **15 passed**, including owner reset/accountant load, case verification and failed-save recovery, approvals and combined vendor exposure, evidence tabs, Roman Urdu, upload confidence/vendor recovery, cash assumptions/scenarios/drill-down, dashboard retry and measured study, sidebar animation/persistence, keyboard and mobile navigation.
- Additional browser audit: downloaded a **29-line demo bank CSV**, verified live lines become `exported` and none become `released`; mobile case detail has no horizontal overflow. Desktop run/dashboard and mobile case screenshots were visually inspected.
- Offline: `python -m ml.review_evaluate` and `python -m ml.cash_review` completed and wrote additive, provenance-validated artifacts. Original production artifacts remain unchanged.

The browser verification run initially found unstable form labels after input, which were corrected using explicit sibling labels. The final complete browser suite passes.

## Remaining limits and deferred proposals

- No Gemini key is configured here: live varied-layout Gemini extraction accuracy was not measured. PDF text/OCR/regex and the existing extraction workflow are tested; generated summaries use the labelled fallback.
- PostgreSQL, public deployment URLs, presentation-device timing and a video recording still require their own validation. Local tests use isolated SQLite and system Chromium.
- The current audit log is inspectable, not tamper-proof; bank export is a masked demo CSV, not payment settlement.
- Interviews, a named first customer, willingness to pay and real pilot impact require evidence from people. The guide clearly labels price and buyer assumptions.
- Unseen-fraud/cold-start studies, cash-panel caching, payment deferral, ERP imports, reconciliation, WhatsApp workflows and lender distribution were deferred to preserve a working focused demo. None are represented as shipped features.

## Exact changed-file inventory

### Repository documentation

- [README.md](../README.md)

### backend

- [backend/app/api/core.py](../backend/app/api/core.py)
- [backend/app/api/finance.py](../backend/app/api/finance.py)
- [backend/app/config.py](../backend/app/config.py)
- [backend/app/schemas/requests.py](../backend/app/schemas/requests.py)
- [backend/app/services/cases.py](../backend/app/services/cases.py)
- [backend/app/services/cash/inputs.py](../backend/app/services/cash/inputs.py)
- [backend/app/services/cash/service.py](../backend/app/services/cash/service.py)
- [backend/app/services/docreader/gemini.py](../backend/app/services/docreader/gemini.py)
- [backend/app/services/payment_runs.py](../backend/app/services/payment_runs.py)
- [backend/app/services/scoring/reasons.py](../backend/app/services/scoring/reasons.py)
- [backend/app/services/scoring/review.py](../backend/app/services/scoring/review.py)
- [backend/app/services/scoring/rules.py](../backend/app/services/scoring/rules.py)
- [backend/app/services/scoring/scorer.py](../backend/app/services/scoring/scorer.py)
- [backend/app/services/summary.py](../backend/app/services/summary.py)
- [backend/ml/cash_review.py](../backend/ml/cash_review.py)
- [backend/ml/evaluate.py](../backend/ml/evaluate.py)
- [backend/ml/review_evaluate.py](../backend/ml/review_evaluate.py)
- [backend/tests/conftest.py](../backend/tests/conftest.py)
- [backend/tests/test_cash_collection_policy.py](../backend/tests/test_cash_collection_policy.py)
- [backend/tests/test_finance_regressions.py](../backend/tests/test_finance_regressions.py)
- [backend/tests/test_review_controls.py](../backend/tests/test_review_controls.py)
- [backend/tests/test_review_finance_api.py](../backend/tests/test_review_finance_api.py)
- [backend/tests/test_review_scoring.py](../backend/tests/test_review_scoring.py)
- [backend/tests/test_upload_demo_controls.py](../backend/tests/test_upload_demo_controls.py)

### frontend

- [frontend/e2e/audit-ui.spec.ts](../frontend/e2e/audit-ui.spec.ts)
- [frontend/e2e/case-verification.spec.ts](../frontend/e2e/case-verification.spec.ts)
- [frontend/e2e/cash-policy.spec.ts](../frontend/e2e/cash-policy.spec.ts)
- [frontend/e2e/demo-polish.spec.ts](../frontend/e2e/demo-polish.spec.ts)
- [frontend/e2e/happy-path.spec.ts](../frontend/e2e/happy-path.spec.ts)
- [frontend/e2e/rules-comparison.spec.ts](../frontend/e2e/rules-comparison.spec.ts)
- [frontend/e2e/vendor-workflows.spec.ts](../frontend/e2e/vendor-workflows.spec.ts)
- [frontend/src/app/(app)/cases/[id]/page.tsx](../frontend/src/app/(app)/cases/[id]/page.tsx)
- [frontend/src/app/(app)/cash/page.tsx](../frontend/src/app/(app)/cash/page.tsx)
- [frontend/src/app/(app)/dashboard/page.tsx](../frontend/src/app/(app)/dashboard/page.tsx)
- [frontend/src/app/(app)/flagged/page.tsx](../frontend/src/app/(app)/flagged/page.tsx)
- [frontend/src/app/(app)/run/page.tsx](../frontend/src/app/(app)/run/page.tsx)
- [frontend/src/components/app/case-verification.tsx](../frontend/src/components/app/case-verification.tsx)
- [frontend/src/components/app/cash-panel.tsx](../frontend/src/components/app/cash-panel.tsx)
- [frontend/src/components/app/cash-validation-note.tsx](../frontend/src/components/app/cash-validation-note.tsx)
- [frontend/src/components/app/decision.tsx](../frontend/src/components/app/decision.tsx)
- [frontend/src/components/app/line-sheet.tsx](../frontend/src/components/app/line-sheet.tsx)
- [frontend/src/components/app/review-evaluation.tsx](../frontend/src/components/app/review-evaluation.tsx)
- [frontend/src/components/app/rules-comparison.tsx](../frontend/src/components/app/rules-comparison.tsx)
- [frontend/src/components/app/shell.tsx](../frontend/src/components/app/shell.tsx)
- [frontend/src/lib/types.ts](../frontend/src/lib/types.ts)

### models

- [models/cash_review_metrics.json](../models/cash_review_metrics.json)
- [models/review_eval.json](../models/review_eval.json)

### docs

- [docs/demo-guide.md](../docs/demo-guide.md)
- [docs/model_card.md](../docs/model_card.md)
- [docs/review-implementation.md](../docs/review-implementation.md)

Total changed files: 51.
