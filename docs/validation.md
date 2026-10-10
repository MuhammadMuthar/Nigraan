# Audit fixes: implementation and verification

Validated 10 October 2026 against current main, including the flagged-invoices, dark-mode and preferences changes already merged there.

## Changes

- Prevent repeat/concurrent invoice scheduling and bank-file export with atomic server-side claims; enforce confirmed drafts, finite/nonnegative exact paisa, and invoice total reconciliation.
- Represent CSV generation as exported and unsettled. Retain each obligation once in cash projections and recover live false-alarm cases after export without exporting previous instructions again. Preserve historical settlements.
- Validate malformed imports before writes with row/field feedback, and extract scanned PDFs through bounded Poppler/Tesseract OCR. Include Poppler in the API image.
- Complete role-aware vendor creation, upload matching and independent bank-change approval with the existing APIs.
- Add persistent sidebar minimization with a 220ms width transition, accessible icon links and reduced-motion support; retain mobile left-sheet closing animations and main's preferences.
- Fix cash chart click/keyboard drill-down and signed tooltips, add error/retry states, guard stale requests through the existing cache and force explicit retries. Preserve paisa when displaying money.
- Describe calibrated scores and demo bank exports honestly; add a five-minute presentation guide without invented deployment, traction or ROI claims.

## Validation

| Check | Result |
| --- | --- |
| Frontend typecheck | Passed |
| Frontend lint | Passed, two existing navigation warnings |
| Frontend production build | Passed, 12 routes |
| Backend pytest | 70 passed; existing Starlette/httpx deprecation |
| Isolated full feature/API audit | 126 assertions passed, including actual retrain and real scanned-PDF OCR |
| Playwright Chromium suite | 11 passed (2.1 minutes) |

The isolated audit used a separate SQLite database and copied model artifacts outside the checkout. It covers login/permissions, reset/load, scoring/evidence, case outcomes, vendor APIs, extraction/edit/confirm/score, approval/hold/export, cash/receivables/scenarios, dashboard and retraining. Browser regressions exercise service failure/retry, stale invoice requests, chart clicking and negative balances, sidebar persistence/keyboard/reduced motion, vendor bank-change approval and unmatched-upload recovery.

Live Gemini, PostgreSQL, container build, actual bank settlement, remote deployment, security/load testing and non-Chromium browsers were not validated in this environment. CSV export remains a demo artifact with masked beneficiary details, and there is no settlement integration. Public deployment/video links and customer validation require actual external evidence.

Seven phone-width route checks at 320px passed with no page overflow. The final sidebar screenshots were also inspected.

## Exact changed files

- `README.md`
- `backend/Dockerfile`
- `backend/app/api/core.py`
- `backend/app/api/finance.py`
- `backend/app/models/tables.py`
- `backend/app/schemas/requests.py`
- `backend/app/services/cases.py`
- `backend/app/services/cash/service.py`
- `backend/app/services/docreader/ocr_fallback.py`
- `backend/app/services/docreader/pipeline.py`
- `backend/app/services/importer.py`
- `backend/app/services/payment_runs.py`
- `backend/app/services/scoring/scorer.py`
- `backend/tests/test_finance_regressions.py`
- `backend/tests/test_import_extraction_regressions.py`
- `docs/demo-guide.md`
- `docs/validation.md`
- `frontend/e2e/audit-ui.spec.ts`
- `frontend/e2e/sidebar.spec.ts`
- `frontend/e2e/vendor-workflows.spec.ts`
- `frontend/src/app/(app)/cases/[id]/page.tsx`
- `frontend/src/app/(app)/cases/page.tsx`
- `frontend/src/app/(app)/cash/page.tsx`
- `frontend/src/app/(app)/flagged/page.tsx`
- `frontend/src/app/(app)/run/page.tsx`
- `frontend/src/app/(app)/upload/page.tsx`
- `frontend/src/app/(app)/vendors/[id]/page.tsx`
- `frontend/src/app/(app)/vendors/page.tsx`
- `frontend/src/app/globals.css`
- `frontend/src/components/app/line-sheet.tsx`
- `frontend/src/components/app/shell.tsx`
- `frontend/src/components/app/vendor-create-dialog.tsx`
- `frontend/src/lib/format.ts`
- `frontend/src/lib/hooks.ts`
