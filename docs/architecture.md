# Architecture

```mermaid
flowchart LR
  subgraph Inputs
    PDF[Invoice PDF / image] --> DR
    CSV[ERP CSV export] --> IMP[CSV import]
    REC[(Customer receivables)]
  end

  subgraph DR[Document reader]
    G[Gemini Flash<br/>JSON schema, temp 0] --> V[Pydantic schema +<br/>deterministic checks]
    T[PDF text / Tesseract<br/>+ regex] --> V
    V --> C[Per-field confidence<br/>= agreement + validators]
  end

  C --> INV[(Invoices)]
  IMP --> INV
  INV --> RUN[Weekly payment run]

  subgraph FW[Fraud firewall: every payment line]
    R[Rule layer<br/>hard rules force red]
    D[Duplicate detector<br/>LogReg on pair features]
    X[Risk model<br/>XGBoost + SHAP reasons]
    I[Isolation Forest<br/>unseen patterns]
    N[Relationship graph<br/>NetworkX]
    R & D & X & I & N --> F[Fusion<br/>100 × max(rule, Σ w·signal)]
    F --> DEC{Allow · Review · Blocked}
  end

  RUN --> FW
  DEC -->|red| CASE[Case + evidence<br/>+ guarded LLM summary]
  CASE -->|confirm / false alarm| LBL[(Labels)] --> RT[Retrain]
  RT --> FW

  subgraph CASH[Cash side]
    LM[Late-payment model<br/>XGBoost vs LR vs baseline]
    EX[Expected dates<br/>median customer delay]
    CE[Deterministic 13-week<br/>cash engine, daily]
  end
  REC --> LM & EX --> CE
  DEC -->|green + yellow lines| CE
  CE --> PANEL[Payment-run cash panel<br/>low point, first breach,<br/>receivables to chase]
```

## Principle

ML models and deterministic code decide. The LLM (Gemini) only does two things:
1. reads documents into a strict schema, cross-checked by deterministic validators;
2. writes case summaries from structured evidence, with a number-check guardrail.

It never produces a score, a decision or a cash number.

## Runtime

| Piece | Where |
|---|---|
| API | FastAPI, `backend/app` (routers `api/core.py`, `api/finance.py`), JWT + roles, uniform error envelope |
| Scoring | `services/scoring/*`: features, duplicates, graph, rules, risk (artifacts), fuse, reasons, scorer (trace) |
| Cash | `services/cash/engine.py` (pure), `inputs.py` (flows from tables), `service.py` (panel, outlook, scenarios) |
| Receivables | `services/receivables/late_model.py` (features at issue date, predict, reasons) |
| Document AI | `services/docreader/*` (Gemini, PDF text/OCR + regex, schema/validators, pipeline) |
| Learning loop | `ml/retrain.py`, triggered from `/admin/retrain` (background job) |
| Data | `data_gen/*`: seeded company, frauds, receivables, demo week, PDFs |
| Offline ML | `ml/train_all.py`, `ml/evaluate.py`, `ml/eval_extraction.py` |
| Frontend | Next.js 16 App Router, Tailwind 4, Radix/shadcn-style UI, Recharts, react-force-graph-2d |

Models are loaded once at startup from `models/`. The scoring context (ledger indexes, duplicate index, relationship graph) is cached in process memory and rebuilt when a write bumps the data version. A 40-line run scores in about 1 s, about 8 ms per line after the context is built.

## Data protection

- CNICs and full IBANs are stored only as salted SHA-256 hashes plus the last 4 digits.
- Money is integer paisa end to end.
- Timestamps are stored in UTC and displayed in Asia/Karachi.
- The audit log covers logins, approvals, holds, overrides, bank-change requests and approvals, case views and resolutions, exports, retrains and demo resets.
